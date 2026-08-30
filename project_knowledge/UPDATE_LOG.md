# Update Log

## 2026-08-30 — repository scaffold
- Created repository structure (data/raw, data/processed, data/unified, metadata,
  dictionaries, project_knowledge, scripts, tests, reports, config, .github/workflows).
- Wrote shared pipeline library: raw storage (append-only, date-stamped), metadata
  schema, validation (schema/type/missing/duplicate/frequency/outlier/structural-change
  checks), documented transformations (level/log/diff/growth/YoY/QoQ/MoM/deflate/rebase),
  revision tracking, unified long+wide dataset builder, structured run logging.
- Wrote `update_bns.py` / `update_nbk.py` / `update_minfin.py` / `update_imf.py` /
  `update_all.py` orchestrators. No real fetchers implemented yet — every indicator
  currently logs `status=skipped` because no source has been confirmed. This is
  intentional: MASTER TASK rules forbid guessing an API/endpoint/dataset structure.
- Wrote unit tests for the parts that don't depend on live data (transformations,
  validation, revisions, unified dataset pivot, and orchestrator skip-behavior).
- Launched source research for all 4 agencies (BNS, NBK, Minfin, IMF) against the
  15-20 stage-1 indicators in `config/indicators.yaml`. Results will populate
  `config/sources.yaml`, `SOURCES.md`, and unlock real fetchers per indicator.

## 2026-08-30 — source research complete, 8/18 indicators connected end-to-end
- Source research finished for all 4 agencies with real, live-verified URLs (curl'd,
  downloaded, and in several cases unzipped/parsed to confirm structure) — recorded in
  `config/sources.yaml`. No endpoint, dataset ID, or column layout in that file was guessed.
- Implemented real fetchers and ran the full pipeline (download -> raw archive -> validate
  -> process -> metadata -> unified dataset -> tests -> report) against live sources for:
  BNS CPI (monthly, MoM), BNS UNEMPLOYMENT (quarterly, national), BNS GDP_NOMINAL (quarterly,
  cumulative YTD as published), NBK BASE_RATE (event-dated), NBK EXCHANGE_RATE (daily
  USD/KZT, last 14 days), IMF_GDP_GROWTH, IMF_INFLATION, IMF_CURRENT_ACCOUNT (WEO, annual).
- 10 indicators remain not connected, each for a documented reason in `config/sources.yaml`
  and `DATA_DICTIONARY.md`'s "Not yet connected" section: GDP_REAL (no machine-readable
  series located yet), BNS IND_PROD/INVESTMENT (URL confirmed, cube structure not yet
  parsed), BNS EXPORTS/IMPORTS (XLSX-only, not yet parsed), NBK M2/M3 (URL confirmed, but
  the row_code -> M2/M3 mapping needs the downloaded metadata XLSX parsed first), Minfin
  GOV_REVENUE/GOV_EXPENDITURE/GOV_DEBT (XLSX source confirmed and downloaded/inspected, but
  automated cell-level parsing deliberately not implemented yet -- sheet layout can shift
  between bulletin editions and a wrong guess would silently produce a wrong total).
- `pytest tests/ -q` — 24/24 passing.
- Wrote `scripts/build_project_knowledge.py` to auto-regenerate DATA_CATALOG.md,
  DATA_DICTIONARY.md, SOURCES.md, and latest/{macro_latest.csv,macro_metadata.json} from
  the current metadata/ + config/ state after every pipeline run.

## 2026-08-30 — re-verified 3 open questions before widening scope, 10/18 connected
Prompted by a review asking to check three specific claims rather than accept them at
face value. All three were re-checked live rather than reasoned about from memory:
- **GDP_REAL**: the earlier "not found" conclusion was premature. Taldau (a separate
  system from the /open-data/ file API) does publish it as "индекс физического объема
  ВВП" (indexId 2979005 production-method, 700974 final-use-method) — confirmed by
  reading Taldau's own category page. However its delivery mechanism is a full internal
  ExtJS single-page app with a stateful, multi-step AJAX protocol, not a one-shot file
  download. Reverse-engineered the term tree and found a real JSON export endpoint that
  responds HTTP 200 (so not CAPTCHA/login-blocked), but every parameter combination tried
  returned an empty result — the client evidently accumulates state across several prior
  AJAX calls before that endpoint returns data. Status is now `found_but_not_yet_parseable`
  (not `not_found`) in `config/sources.yaml`, with the exact endpoints/params tried recorded
  so the next attempt doesn't repeat this work blind.
- **IND_PROD / INVESTMENT**: re-checked by actually downloading and parsing the full files
  (previously only HEAD-checked). Both turned out to be the identical simple json_cube
  format already used for GDP_NOMINAL/UNEMPLOYMENT — not a harder merged-cell pivot table.
  This was genuinely "didn't get to it yet," not a harder technical problem, so both are
  now implemented (`scripts/fetchers/bns.py:fetch_ind_prod`, `fetch_investment`) and
  connected. Two real findings surfaced by actually parsing the data: both files contain
  only annual points (not monthly/quarterly as originally assumed in `indicators.yaml` —
  corrected); INVESTMENT's national-total combo appears as two non-overlapping cube slices
  (2016-2018 and 2019-2022), which looks like a methodology break — concatenated with the
  break recorded in metadata rather than silently smoothed over.
- **Cron schedule**: confirmed `.github/workflows/update.yml` already had a concrete value
  (`0 6 * * *`, daily at 06:00 UTC) — describing it as a "placeholder" in the stage-1 summary
  was imprecise phrasing on my part, not an actual gap. Reworded the comment so it reads as
  the deliberate default it is, and grounded the rationale in the confirmed NBK publication
  calendar and observed BNS/Minfin cadence from `config/sources.yaml`.
- 10/18 indicators now connected end-to-end (up from 8/18): added BNS IND_PROD and
  INVESTMENT. Remaining 8 not connected: GDP_REAL (found, not yet parseable — see above),
  BNS EXPORTS/IMPORTS (XLSX-only), NBK M2/M3 (row_code mapping unresolved), Minfin
  GOV_REVENUE/GOV_EXPENDITURE/GOV_DEBT (XLSX, cell-level parsing not yet implemented).
- `pytest tests/ -q` — 24/24 passing after the changes.
- Pushed to https://github.com/makenerzhan-gif/kazakhstan-economic-data (private repo,
  already existed empty under the user's account).

## 2026-08-30 — all 18/18 stage-1 indicators connected
Tackled the remaining 8: GDP_REAL's Taldau AJAX flow, Minfin XLSX parsing (all 3), and
NBK M2/M3 row mapping (BNS EXPORTS/IMPORTS were also outstanding but turned out
straightforward once actually attempted).
- **GDP_REAL** (the hard one): cracked by using the Claude Browser tool to instrument
  XMLHttpRequest in a real session, load the Taldau page, and capture the ACTUAL request
  its own ExtJS grid makes to `POST /ru/NewIndex/GetIndexTreeData`. The earlier blind
  attempts had hit the wrong endpoint and were missing `p_measure_id` plus the real meaning
  of `p_dicIds` (a classifier-dictionary id, not a term id). Independently re-verified with
  a plain, cookie-less `requests.post` — fully stateless, no session/auth needed. Now
  connected: physical volume index of GDP, production method, annual, 2000-2025.
- **NBK M2/M3**: the row_code -> M2/M3 mapping wasn't in any API response or the metadata
  XLSX (which explains the M0-M3 concepts but has no code column). Resolved by opening the
  human-facing table at nationalbank.kz in a real browser: its numbered rows ("4. M2", "5.
  M3") match `row_code` exactly, confirmed both structurally and by matching numeric values
  1:1 against the API. row_code=4 -> M2, row_code=5 -> M3.
- **BNS EXPORTS/IMPORTS**: XLSX-only, downloaded and parsed directly (54MB/93MB — large
  because BNS republishes full history every month, not deltas). National monthly total is
  literally row 4 of each year-sheet, labeled "Республики Казахстан". Set up **Git LFS** for
  `data/raw/bns/*.xlsx` and `data/raw/minfin/*.xlsx` (user's choice, asked explicitly given
  the ~1GB/year growth these two files alone would add to plain git history).
- **Minfin GOV_REVENUE/GOV_EXPENDITURE**: found a much safer source than the 50-sheet
  monthly bulletin — a small, purpose-built "Dynamics of execution of the republican budget"
  document (97KB), with the republic-level total on stable row labels ('I. INCOME',
  'II.Expences'). Discovered dynamically by title each run, not hardcoded. Frequency
  corrected to annual (was assumed monthly).
- **Minfin GOV_DEBT**: no combined dynamics file exists for debt, so this backfills from 23
  individual quarterly snapshot documents. Cross-checked 3 vintages (2021/.xls, 2024/.xlsx,
  2026/.xlsx) to confirm the target row's LABEL text is stable even though its position and
  column offset shift between editions — so the parser searches by label, not a fixed index.
  17/23 documents parsed (6 skipped — older/differently-templated files); real gaps exist in
  the resulting series (not interpolated). Values converted from the source's thousand-KZT
  unit to million KZT for consistency with revenue/expenditure.
- **18/18 stage-1 indicators now connected end-to-end.** `pytest tests/ -q` — 24/24 passing.
- Also corrected GOV_REVENUE/GOV_EXPENDITURE frequency from monthly to annual once their
  real source was found (see above).

## 2026-08-30 — first scale-up batch: 18 -> 37 indicators
User asked to scale toward the master task's eventual 100-150 indicator list. Proposed a
categorized ~25-indicator next batch (shared before researching, per the user's preference);
19 were connected, 4 hit genuine dead ends (documented, not silently dropped).

**Research method note:** the 4 parallel research subagents launched for this batch all
failed immediately on a session usage limit ("You've hit your session limit"). Rather than
retry the subagent mechanism, did the remaining research directly (Bash/WebSearch/WebFetch)
for the rest of this batch -- same rigor, just no subagent parallelism.

**Connected (19):**
- 8 BNS national-accounts indicators via Taldau, reusing (and generalizing) the exact
  mechanism cracked for GDP_REAL: GDP_PER_CAPITA, GDP_DEFLATOR, GFCF, GFCF_VOLUME_INDEX,
  NET_EXPORTS, HOUSEHOLD_CONSUMPTION, COMPENSATION_EMPLOYEES, AVG_WAGE. The last one
  (AVG_WAGE) needed a second round of browser XHR capture -- it's classified across 5
  dictionaries at once (region+industry+locality+size+sex), not just region, so the
  single-dimension GDP_REAL params (measure_id=7, dicIds=67) 500'd; captured the real
  5-dictionary request the same way as GDP_REAL and generalized `_fetch_taldau_annual_index`
  to accept measure_id/terms/dic_ids overrides.
- 5 NBK indicators: MONETARY_BASE/M0/M1 (same formId=51 dataset as M2/M3, just different
  row_code, verified against the human table the same way). FX_RESERVES and
  NATIONAL_FUND_ASSETS were both found in a single new dataset (formId=34) discovered while
  researching reserves -- confirmed via an exact internal-sum check (monetary gold + assets
  in CFC = the total row, to the cent, for a sample date).
- 3 Minfin indicators: GOV_HEALTH_SPENDING, GOV_EDUCATION_SPENDING, GOV_SOCIAL_SPENDING --
  functional-breakdown rows from the same small "Dynamics" file already used for
  GOV_REVENUE/GOV_EXPENDITURE, no new source needed.
- 3 IMF WEO indicators: IMF_UNEMPLOYMENT (LUR), IMF_GOV_BALANCE (GGXCNL_NGDP),
  IMF_GOV_DEBT (GGXWDG_NGDP) -- all standard WEO codes, verified live, worked on first try.

**Not connected, documented in `config/sources.yaml` (4):**
- PPI (industrial producer price index): the confirmed page/elementId (1626) is stale in
  CSV (data stops in 2013) and the JSON variant is malformed at the source (confirmed via a
  full, untruncated download matching Content-Length exactly -- not a network issue on our
  end). Checked 3 nearby elementIds; all are other price indices, not industrial PPI.
- DEPOSIT_RATE / LENDING_RATE: both NBK datasets (formId 268, 486) are real and live but
  have no aggregate/total row across their dimensions (agent x currency x term, etc.) --
  picking one specific cross-tab cell and calling it "the" rate would be misleading without
  further research into which combination is the conventional headline figure.
- RETAIL_TRADE, CONSTRUCTION: not resolved to a working source this session (retail trade's
  Taldau category didn't show an obvious turnover series; construction wasn't researched at
  all, deprioritized after the above took longer than budgeted).

**Sanity-checked before committing:** confirmed a real (not fabricated) 2010-2013 gap
present consistently across GFCF/NET_EXPORTS/HOUSEHOLD_CONSUMPTION but absent from
GDP_DEFLATOR/GDP_PER_CAPITA in the same Taldau category (likely a national-accounts
methodology revision that left those specific series unpublished for that window);
confirmed NET_EXPORTS' 2001-2002 negative values are real (pre-oil-boom Kazakhstan), not a
sign error. `pytest tests/ -q` — 24/24 passing (still no network calls). **37/37 confirmed
indicators connected end-to-end.**

## 2026-08-30 — second scale-up batch: 37 -> 58 indicators
User said to continue. This round prioritized near-zero-risk extensions of sources already
proven in the previous two batches, rather than new research: unused rows in the Minfin
"Dynamics" file already downloaded, and unused Taldau national-accounts indexIds already
found while researching GDP_REAL.

**Connected (21), all reusing already-proven mechanisms, no new source discovery:**
- 10 more Minfin fiscal indicators from the SAME Dynamics file as GOV_REVENUE/EXPENDITURE/
  health/education/social spending -- TAX_REVENUE, CORPORATE_TAX, VAT_REVENUE,
  GOV_DEFENSE_SPENDING, GOV_GENERAL_SERVICES_SPENDING, GOV_TRANSPORT_SPENDING,
  GOV_DEBT_SERVICING, NET_BUDGET_LENDING, BUDGET_DEFICIT, NON_OIL_BUDGET_DEFICIT. Had to be
  careful with substring matching -- 'BUDGET DEFICIT (SURPLUS)' alone would have ambiguously
  matched both 'V. BUDGET DEFICIT (SURPLUS)' and 'VI. NON-OIL BUDGET DEFICIT (SURPLUS)'.
- 11 more BNS national-accounts indicators via the same single-region-dimension Taldau
  mechanism as GDP_REAL (measure_id=7, dicIds=67) -- GDP_INCOME_METHOD, GROSS_OUTPUT,
  TAXES_ON_PRODUCTS, NET_TAXES_ON_PRODUCTS, SUBSIDIES, INTERMEDIATE_CONSUMPTION,
  GROSS_ACCUMULATION, IMPORT_VOLUME_INDEX, EXPORT_VOLUME_INDEX,
  TOTAL_CONSUMPTION_EXPENDITURE, CAPITAL_CONSUMPTION.

**Sanity-checked before committing:**
- GDP_INCOME_METHOD's 2025 value matches GDP_NOMINAL (production method) EXACTLY
  (159,608,552,900,000 both) -- GDP measured two different ways landing on the identical
  total is a strong independent cross-check, not a coincidence.
- Confirmed TAXES_ON_PRODUCTS minus SUBSIDIES does NOT equal NET_TAXES_ON_PRODUCTS exactly
  (documented in sources.yaml) -- this is real SNA methodology (SUBSIDIES here is the
  broader production+import concept, not the narrower product-specific one that actually
  nets against NET_TAXES_ON_PRODUCTS), not a data error. Flagged so nobody tries to
  reconcile the three and concludes something's broken.
- Idempotency re-check: re-running update_all.py touched only manifests/logs/reports (which
  carry timestamps) and the regenerated unified dataset -- zero actual data-file churn.

**58/58 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 24/24 passing.

## 2026-08-30 — third scale-up batch: 58 -> 67 indicators
Continued after the CI-observability and raw_store fixes were verified end-to-end (see the
separate CI incident entries). This batch covers NBK's remaining monetary/external categories
and 6 more IMF WEO series.

**Connected (9):**
- **IMF WEO** (6, standard codes, all worked first try): IMF_POPULATION (LP),
  IMF_NOMINAL_GDP (NGDP, national currency), IMF_NOMINAL_GDP_USD (NGDPD), IMF_GDP_PPP
  (PPPGDP), IMF_INVESTMENT_RATIO (NID_NGDP), IMF_SAVINGS_RATIO (NGSD_NGDP). Cross-check:
  IMF_NOMINAL_GDP's 2024 value (136,693,318,000,000 KZT) matches our own BNS GDP_NOMINAL
  series (136,693,318,300,000) to within 0.0000002%.
- **NBK REER/NEER** (formId=299): unlike deposit/lending rates, the *effective* exchange
  rate categories turned out to be clean basket-wide indices with no currency-pair
  dimension -- no aggregation risk. Used "Including oil trade" as primary.
- **NBK DEPOSITS_TOTAL** (formId=62, row_code=1): resolved the same way as the M2/M3/
  monetary-base row_code mapping -- cross-referenced the human-facing table and confirmed
  matching values (44,457,125.21 vs the page's 44,457,125).

**Not connected, documented (3), all for the same underlying reason:**
- NBK EXTERNAL_DEBT (checked both formId=358 and the plain-sounding formId=293 "External
  Debt") and NBK LOANS_TO_ECONOMY (formId=445): neither has an aggregate/total row across
  their dimensions, and EXTERNAL_DEBT's `investment_type` field shows what look like
  duplicate categories differing only by trailing whitespace -- computing our own sum was
  judged too risky (real double-counting risk, not just tedious). Same category of gap as
  DEPOSIT_RATE/LENDING_RATE from the second batch.

**Sanity-checked before committing:** REER (123) sits consistently above NEER (82) for the
same recent months -- expected direction given Kazakhstan's inflation has generally
exceeded its trading partners' over the base period, not a sign of a swapped calculation.
DEPOSITS_TOTAL (50.1M) sits between M2 (48.1M) and M3 (55.0M) for the same date --
structurally sensible given deposits-only vs. cash-inclusive aggregate definitions.

**67/67 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — fourth scale-up batch: 67 -> 72 indicators
Continued via the same IMF WEO mechanism as the prior two batches (standard codes, no new
source discovery needed). Also spent significant time on BNS retail trade turnover via
Taldau, without success (see below) -- left undecided rather than guessed.

**Connected (5), all standard IMF WEO codes, verified live:**
- IMF_GOV_REVENUE_RATIO (GGR_NGDP) and IMF_GOV_EXPENDITURE_RATIO (GGX_NGDP), general
  government revenue/expenditure as % of GDP.
- IMF_EXPORT_VOLUME_GROWTH (TX_RPCH) and IMF_IMPORT_VOLUME_GROWTH (TM_RPCH), volume growth
  rates (not values), % change.
- IMF_CURRENT_ACCOUNT_USD (BCA), current account balance in USD level -- companion to the
  already-connected IMF_CURRENT_ACCOUNT (% of GDP).

**Sanity-checked before committing:**
- GGR_NGDP minus GGX_NGDP reproduces IMF_GOV_BALANCE (GGXCNL_NGDP) to within rounding for
  every shared year (e.g. 2031: 19.566% - 21.282% = -1.72%, matching GGXCNL_NGDP's own
  -1.72%) -- three independently-fetched WEO series agreeing internally.
- BCA (USD level) divided by NGDPD (nominal GDP, USD) reproduces BCA_NGDPD
  (IMF_CURRENT_ACCOUNT, % of GDP) almost exactly for every shared year (e.g. 2031:
  -$9.953bn / $501.68bn = -1.984%, matching -1.984% essentially exactly).
- Idempotency: re-running update_all.py touched only manifests (fresh `downloaded_at`
  timestamps, same-day content unchanged), logs, reports, and the regenerated unified
  dataset -- zero raw content-file churn.

**Investigated, not connected, no guess made:** BNS retail trade turnover ("Товарооборот
розничной торговли") via Taldau. Found three candidate indexIds via web search (704502,
701830, 703076). 704502 returns live data with the standard single-dimension mechanism
(measure_id=7, dicIds=67) but the values (~0.27-0.34, dimensionless, 2001-2024) don't look
like turnover in billions of tenge -- almost certainly a different indicator (a ratio or
coefficient), not retail trade. 701830 and 703076 both return HTTP 500 under the standard
mechanism, meaning (like AVG_WAGE) they likely need a non-default measure_id/dicIds
combination discoverable only via live-page XHR capture. Did not guess a mechanism or
substitute an unverified indexId. Left for a future session with fresh browser-capture
budget, or to be documented as `RETAIL_TRADE_NOT_CONNECTED` alongside the other
no-clean-aggregate gaps if not resolved.

**72/72 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — resolved BNS retail trade: 72 -> 73 indicators
Follow-up within the same day: went back to the investigation logged as "not connected"
above and resolved it, per explicit instruction to finish it rather than move on.

**Connected (1):**
- RETAIL_TRADE: found the correct index via Taldau's own site search API (POST
  /ru/Search/getSearchPageGridData, keyword="розничной торговли") rather than continuing to
  guess from web-search indexIds -- the earlier candidates (701830, 703076) were both wrong
  (701830 turned out to be an unrelated fixed-capital-investment series). The real
  indicator, id=702038 ("Объем розничной торговли в стоимостном выражении", code 171202),
  is classified across 3 dictionaries (region, ownership form, goods type) like AVG_WAGE,
  and also 500'd under the default single-dimension guess. Cracked without a fresh XHR
  capture this time: read the already-loaded page's live ExtJS component tree directly
  (`Ext.ComponentQuery.query('treepanel')` -> the indexTreeGrid store's
  `lastOptions.params`) to recover the exact working request params (measure_id=1,
  dicIds=67,59,676, terms=741880,741907,741894) instead of trial-and-error guessing.

**Sanity-checked before committing:** values run ~558 billion KZT (2000) to ~27.7 trillion
KZT (2025) -- plausible scale and monotonic growth for nominal retail turnover. 2024->2025
nominal growth (~17.6%) is higher than BNS's own cited *real* (inflation-adjusted) growth
figures for the sector (~7%) -- expected, since this series is in value/nominal terms and
therefore also reflects price inflation, not a discrepancy.

**73/73 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — fifth scale-up batch: 73 -> 91 indicators
Broadest single batch so far, spanning all four agencies. Proposed a ~23-candidate list
across BNS/NBK/Minfin/IMF up front, researched each live, connected 18 (2 candidates from
the original list -- POVERTY_RATE, individual-income/property/customs taxes, and
HOUSING_COMMISSIONED -- turned out not to have a clean matching series or fetcher-ready
structure and were left not_connected rather than forced in; NATIONAL_FUND_TRANSFERS wasn't
reached given time budget).

**IMF WEO (6), same proven mechanism, all standard codes:** IMF_GDP_PER_CAPITA_PPP (PPPPC),
IMF_GDP_WORLD_SHARE_PPP (PPPSH), IMF_INFLATION_EOP (PCPIEPCH), IMF_GOV_NET_DEBT_RATIO
(GGXWDN_NGDP), IMF_GDP_DEFLATOR_INDEX (NGDP_D), IMF_REAL_GDP (NGDP_R). Tried LE (employment
level) first -- returned 2 rows with empty OBS_VALUE for Kazakhstan in this vintage, dropped
rather than forced in. Cross-check: IMF_GOV_NET_DEBT_RATIO (8.99% of GDP, 2031) sits well
below IMF_GOV_DEBT's gross figure (32.11%), consistent with Kazakhstan's National Fund
assets offsetting gross liabilities.

**NBK (3), resolving three gaps explicitly logged as not_connected in earlier batches:**
- EXTERNAL_DEBT: found via `GET /api/v1/data/categories` (a full form catalog by human name,
  not used in earlier attempts) -- formId=353's "Absolute indicators - External debt" row
  (period='quarter' only) is a genuinely pre-aggregated headline total, unlike the two forms
  checked previously (358, 293). 85 rows, 2005-Q2 to 2026-Q2.
- LENDING_RATE / DEPOSIT_RATE: re-investigated the same forms flagged not_connected before
  (486, 268) plus a new one (27) -- found that formId=27 carries an explicit `agg_level`
  field (agg_level='1' = NBK's own currency-only-split aggregate) and formId=268's null
  deposit_term/deposit_type values are NBK's own "all terms/types" aggregation, not missing
  data. Used national-currency headline figures for both (56 and 43 monthly rows
  respectively). Sanity-checked: DEPOSIT_RATE (~14.7%) < BASE_RATE (16.75%) <
  LENDING_RATE (~20.8%) -- correct spread ordering.
- Caught and fixed a pagination bug during EXTERNAL_DEBT research: the API's `page` param is
  0-indexed and must be driven by the response's own `totalRows` field -- an off-by-one
  manual-testing script (page starting at 1) silently truncated results by ~500 rows before
  being caught by comparing against `totalRows`. The actual codebase's existing pagination
  (in fetch_fx_reserves etc.) was already correct; only ad-hoc research scripts had the bug.
- LOANS_TO_ECONOMY remains not_connected: also checked formIds 488/493 ("analytical
  representation") this batch -- both are pure microdata with no agg_level-style field and
  no null-as-aggregate pattern. No further formIds identified to try.

**BNS (6), all via Taldau's site search API (proven for RETAIL_TRADE) plus the live-ExtJS-
tree param-recovery technique (proven for AVG_WAGE/RETAIL_TRADE) for each multi-dictionary
index:** CONSTRUCTION (701885, resolves the "not researched" gap), POPULATION_BNS (703834,
average annual population), REAL_WAGE_INDEX (702976, inflation-adjusted companion to
AVG_WAGE), EMPLOYED_TOTAL (702840, companion to UNEMPLOYMENT), BIRTHS_TOTAL (703839),
DEATHS_TOTAL (703847). Cross-check: POPULATION_BNS's 2025 value (20,391,610.5) matches the
already-confirmed IMF_POPULATION (20,380,366) to within 0.06% -- two independent agencies
agreeing almost exactly. HOUSING_COMMISSIONED (701938) was found but left not_connected: its
period_id is 8 (monthly-cumulative) rather than 7 (annual) like every other connected BNS
Taldau indicator, and its date keys don't fit the shared annual-index helper's parsing logic
without a real risk of silent date collisions -- left for a dedicated parser in a future
session rather than rushed in.

**Minfin (3), same "Dynamics" file as TAX_REVENUE/CORPORATE_TAX/VAT_REVENUE and same
quarterly debt-snapshot documents as GOV_DEBT:** EXCISE_TAX_REVENUE (the third and last
tax-type row in the Dynamics file). GOV_DEBT_DOMESTIC / GOV_DEBT_EXTERNAL (the "1.1.
internal:" / "1.2. external:" breakdown of the "Republic of Kazakhstan Government Debt"
line -- found by printing every column of a real document, since the descriptive label
lives in the row's second cell, not the first). Verified: domestic (28.47T KZT) + external
(8.35T KZT) = 36.82T KZT, matching that line's own total to 5 decimal places -- but
explicitly documented as a NARROWER concept than GOV_DEBT itself (40.92T KZT, which also
includes State Guarantees and Subsidiary Liabilities), so the three won't sum together.
Individual income tax, property tax, and customs duties are not present in the Dynamics
file and would require the much larger (50-sheet) monthly Statistical Bulletin -- not
attempted this session given its documented structural-shift risk.

**91/91 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — sixth scale-up batch: 91 -> 99 indicators
Proposed ~15 candidates across BNS/NBK/IMF up front (Minfin dropped from the proposal after
NBK's National Fund research turned up a better answer than a Minfin-side search would
have). Connected 8; industrial-production sub-indices (mining/manufacturing/electricity) and
POVERTY_RATE were searched for on Taldau with several phrasings and not found, left
not_connected rather than guessed.

**BNS (2), both resolving indicators found in the previous batch but left not_connected
because they didn't fit the existing annual-index parser:**
- PPI: abandoned the stat.gov.kz open-data route entirely (stale/malformed at the source,
  per the original not_connected notes) in favor of Taldau, found via site search (indexId
  703039). Same period_id=8 ("month with accumulation") complication as
  HOUSING_COMMISSIONED, but a cumulative AVERAGE not a SUM here -- confirmed non-monotonic
  within a year (2025: Jan=109.4 declining to Dec=107.1), which is itself the confirmation
  that December is BNS's own standard annual PPI figure (same convention as CPI's annual
  number).
- HOUSING_COMMISSIONED: built a shared `_fetch_taldau_annual_from_monthly_cumulative` helper
  (used by both PPI and this) that extracts only the December year-to-date-cumulative key
  per year as the annual total, instead of forcing period_id=8 data through the plain-annual
  helper (which would have silently collided multiple months onto one date). Confirmed this
  series is a genuine cumulative SUM (monotonically non-decreasing within 2025: Jan=38 ...
  Dec=986.2), a different cumulation type than PPI -- documented explicitly since the two
  indicators route through the same helper but mean different things.

**NBK (3), all newly discovered this batch, none previously attempted:**
- TONIA: NOT a formId-keyed Open Data form -- found via `/api/v1/data/indicators`, the small
  endpoint backing the homepage's own headline widget. Only a rolling ~6-month history is
  available (confirmed empty for 2020/2015 date ranges) -- documented as a real endpoint
  limitation, not a bug.
- NATIONAL_FUND_TRANSFERS: formId=470's `data_type='Transfers from National fund'` is a
  clean single-dimension series once the right data_type value was identified from the
  form's own catalog listing.
- KASE_USD_VOLUME: formId=35 (KASE trading results) is multi-dimensional overall, but
  picking type='Volume of trade...' + currency='US dollars' isolates a clean single series
  without summing across currencies.

**IMF WEO (3), level-value companions to ratios already connected:**
IMF_GOV_EXPENDITURE (GGX) and IMF_GOV_REVENUE (GGR) -- national-currency levels behind
IMF_GOV_EXPENDITURE_RATIO/IMF_GOV_REVENUE_RATIO, cross-checked by dividing through
IMF_NOMINAL_GDP and matching the ratio series to within rounding. IMF_CPI_INDEX (PCPI) --
index level behind IMF_INFLATION's % change. Tried NID/NGSD (investment/savings levels)
first; both returned zero populated rows for Kazakhstan (only their _NGDP ratio variants
exist), so neither was forced in.

**Sanity-checked before committing:** GGX/NGDP and GGR/NGDP both reproduce their respective
ratio series' 2031 values to within rounding. HOUSING_COMMISSIONED's December key confirmed
monotonic within-year (a sum); PPI's confirmed non-monotonic within-year (a cumulative
average) -- the two behaviors distinguished explicitly rather than assumed identical just
because they share a fetcher.

**99/99 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — seventh scale-up batch: 99 -> 108 indicators
Crossed the master task's 100-indicator mark this batch. Proposed BNS trade/transport/
environment companions, NBK remittances, and IMF level-companions up front; agriculture
output and education enrollment were searched for but not found, left unconnected.

**BNS (5), all via Taldau site search + live-ExtJS-tree param recovery (by now a routine
mechanism):**
- WHOLESALE_TRADE (702020) -- direct companion to RETAIL_TRADE, same 3-dictionary shape.
  Cross-checked: 2024 wholesale/retail ratio (~2.0) matches the ~66%/33% split cited in
  independent BNS commentary found during RETAIL_TRADE's own research.
- RETAIL_TRADE_VOLUME_INDEX (702041) -- physical volume companion to RETAIL_TRADE's value
  series.
- EMISSIONS (705070) -- required a real unit correction: the raw API value is in
  KILOGRAMS, not the metric tonnes shown on Taldau's own human-facing summary page.
  Confirmed via an exact /1000 relationship between the two, then converted in the fetcher
  (only on the processed/derived values, raw bytes archived untouched, same pattern as
  Minfin's thousand-to-million-KZT conversion).
- FREIGHT_TURNOVER (702179) and PASSENGER_TURNOVER (702177) -- transport sector companions.

**NBK (2), both via formId=408 ("International remittances by IMTS"):** REMITTANCES_SENT
and REMITTANCES_RECEIVED. Unlike the loan/rate forms from earlier batches, this form
genuinely has an `imts='Total'` pre-aggregated row across all money transfer systems
(MoneyGram, Unistream, Contact, Golden Crown, UPT) -- confirmed present rather than assumed.
Government securities forms (17, 16) were also checked this batch and found to have the same
no-aggregate problem as the loan forms -- not connected.

**IMF WEO (2), level-value companions to ratios already connected:** IMF_GOV_BALANCE_LEVEL
(GGXCNL, national-currency level behind IMF_GOV_BALANCE's % of GDP) and
IMF_PPP_EXCHANGE_RATE (PPPEX, implied PPP conversion rate). Tried BM/BX (imports/exports of
goods, USD level) first; both returned zero populated rows for Kazakhstan, dropped rather
than forced in.

**Sanity-checked before committing:** GGXCNL/NGDP reproduces IMF_GOV_BALANCE's 2031 value
almost exactly. PPPEX (~250 KZT/int'l$) sits well below the market exchange rate (~486
KZT/USD) -- the expected direction for a developing economy's PPP discount. REMITTANCES_SENT
consistently exceeds REMITTANCES_RECEIVED across all 58 months, a stable and plausible
pattern rather than noise.

**108/108 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — eighth scale-up batch: 108 -> 116 indicators
Switched technique for the harder BNS gaps this batch: instead of guessing keyword
phrasings (which had repeatedly failed for agriculture/industrial-sub-sector searches in
earlier batches), browsed the relevant Taldau category pages directly
(GetIndustryByID/<id>) and read off their "main indicators, RK totals" lists. This
immediately found AGRICULTURE_OUTPUT, which multiple keyword phrasings had missed entirely
despite being the very first item on its category's summary page.

**BNS (5):**
- AGRICULTURE_OUTPUT (701189) -- found via category browsing ("Статистика сельского,
  лесного, охотничьего и рыбного хозяйства"). Verified live: matches the category page's
  own displayed 2025 figure (9,704,982.0 million KZT) exactly.
- PER_CAPITA_INCOME (704447) and REAL_INCOME_INDEX (704449) -- found via category browsing
  ("Статистика уровня жизни"). Both worked with the plain single-dimension mechanism
  (measure_id=7, dicIds=67) directly, no live-ExtJS capture needed. POVERTY_RATE was looked
  for on this same category page and confirmed absent from the RK-totals list -- still not
  connected.
- TELECOM_SERVICES (702379) and DOCTORS_TOTAL (704315) -- found via keyword search
  ("связи", "численность врачей"). Industrial-production sub-sector indices (mining/
  manufacturing) were searched for again this batch with several phrasings and still not
  found.

**NBK (2):** INFLATION_EXPECTATIONS (formId=305, a genuinely single-dimension survey
series) and BUSINESS_ACTIVITY_INDEX (formId=339, index_type='Business activity index by
economy' is NBK's own pre-aggregated PMI-style headline). Government securities forms (17,
16) remain not_connected, same no-aggregate problem as before.

**IMF WEO (1):** IMF_STRUCTURAL_BALANCE (GGSB_NPGDP). Tried NGAP_NPGDP (output gap) first;
empty for Kazakhstan, dropped.

**Sanity-checked before committing:** PER_CAPITA_INCOME and REAL_INCOME_INDEX both match
their category page's displayed 2025 figures exactly (238,070 KZT and 98.9% respectively).
Business Activity Index hovers near the neutral 50 mark, as expected for a PMI-style survey
index. Structural balance sits close to but not identical to the headline actual balance
(-1.93% vs -1.97% for 2029) -- the expected small gap between the two measures.

**116/116 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — ninth scale-up batch: 116 -> 123 indicators
Systematically browsed every remaining untouched Taldau category page this batch (external
trade, tourism, education, healthcare, services -- all empty or stale/2008-only) alongside
energy, which had two live current indicators. On the NBK side, checked several forms not
yet explored (Financial Soundness Indicators, non-cash payments, government securities in
circulation) for clean single-value picks.

**BNS (3):** ENERGY_INTENSITY and ENERGY_CONSUMPTION (found via category browsing --
"Статистика энергетики и товарных рынков" was the only one of six browsed categories with
live current data), ELECTRICITY_PRODUCTION (via keyword search, not on the category's own
short RK-totals list). Crude oil/gas production was searched for with several phrasings and
not found on Taldau.

**NBK (3):** NON_CASH_PAYMENTS_SHARE (formId=303, a short but clean 5-row annual series),
CAPITAL_ADEQUACY_RATIO and NPL_RATIO (both from formId=314, NBK's own IMF-standard
Financial Soundness Indicators -- picked already-computed ratios rather than attempting any
aggregation, since NBK publishes the ratios directly). Government securities in circulation
(formId=430) was also checked and found to have the same no-aggregate problem as the loan/
auction forms -- not connected.

**IMF WEO (1):** IMF_CPI_EOP_INDEX (PCPIE), the third leg of the CPI trio alongside
IMF_CPI_INDEX (average-period level) and IMF_INFLATION_EOP (% change).

**Sanity-checked before committing:** ELECTRICITY_PRODUCTION (~113.6-118.7 billion kWh)
matches Kazakhstan's known annual generation scale. ENERGY_CONSUMPTION's 2025 value
(80,050.5) matches the category page's own displayed figure (80,051, rounded) almost
exactly. CAPITAL_ADEQUACY_RATIO (~21.4-21.5%) sits well above the Basel minimum (~8%) and
NPL_RATIO (~2.9-3.3%) at a healthy level -- both plausible for Kazakhstan's banking sector.

**123/123 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — tenth scale-up batch: 123 -> 127 indicators
Resolved the longest-standing open gap from this session: industrial-production sub-sector
indices (mining/manufacturing/electricity), searched for via Taldau keywords in at least
three earlier batches and never found. The fix was to stop searching Taldau and instead go
back to IND_PROD's own already-connected stat.gov.kz source file (element_id=5809) and
enumerate every distinct `industry` value present in it -- 405 total, full product-level
detail, but also the exact top-level NACE-style sections needed. The sub-sector data was
never a separate indicator to find; it was an unexplored dimension of a file already
connected two batches ago.

**BNS (3):** IND_PROD_MINING, IND_PROD_MANUFACTURING, IND_PROD_ELECTRICITY -- same source
file and mechanism as IND_PROD itself, same 15 annual periods (2009-2023), values (~99-106%
range) consistent with the whole-industry aggregate's own range.

**IMF WEO (1):** IMF_GDP_PER_CAPITA_NATIONAL (NGDPPC). Tried TX/TM (exports/imports of goods
and services, USD level) and TXG_D first; all empty for Kazakhstan, none forced in.

**Investigated and left unconnected:** NBK payment cards (formId=18) -- found a
null-as-aggregate pattern similar to earlier NBK wins, but the fully-aggregated rows
contained genuine duplicate (report_date, all-null-dims) pairs with DIFFERENT values and no
tiebreaker field to resolve which is correct -- rather than guess, left unconnected pending
a cleaner resolution. Government securities in circulation, external trade/tourism/
education/healthcare Taldau categories remain empty as established in prior batches.

**Sanity-checked before committing:** IMF_GDP_PER_CAPITA_NATIONAL's 2031 value is consistent
with IMF_NOMINAL_GDP divided by IMF_POPULATION's extrapolated trajectory. Sub-sector indices
sit in the same 99-106% band as the whole-industry IND_PROD aggregate, as expected.

**127/127 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — eleventh scale-up batch: 127 -> 130 indicators
Resolved another long-standing gap this batch: LOANS_TO_ECONOMY, previously not_connected
across four separate raw-loan-microdata forms (445, 4, 488, 493), all lacking any
aggregation field. The fix mirrored IND_PROD_MINING's resolution pattern from the prior
batch -- go back to a form ALREADY connected for a different indicator (formId=314,
Financial Soundness Indicators, used for CAPITAL_ADEQUACY_RATIO/NPL_RATIO) and check its
other `indicator` values rather than searching for a new form. 'Total gross loans' was
sitting right there, already aggregated by NBK itself.

**NBK (1):** LOANS_TO_ECONOMY (formId=314, 'Total gross loans'), converted from the
source's thousand-KZT unit to million KZT for consistency. Also re-investigated the
NBK payment-cards duplicate-row issue flagged in the prior batch -- confirmed genuinely
unresolvable (two rows, identical on every field including report_date, different values,
no revision/vintage marker) -- left unconnected rather than guess.

**BNS (2):** FINAL_ENERGY_CONSUMPTION and RENEWABLE_ENERGY_SHARE, both found on the
"Статистика энергетики" open-data page's own "Динамические ряды" list -- a different
delivery mechanism (stat.gov.kz json_cube, same family as GDP_NOMINAL/IND_PROD) from the
Taldau mechanism used for ENERGY_INTENSITY/ENERGY_CONSUMPTION on the same page. Crude oil
and natural gas production were searched for again this batch (including inside a 41MB,
676-industry BNS open-data file) and still not found -- likely Ministry of Energy
territory, out of BNS's own published scope.

**Sanity-checked before committing:** FINAL_ENERGY_CONSUMPTION sits consistently below
ENERGY_CONSUMPTION (primary) for the same years, the expected direction since final
consumption excludes conversion/transformation losses. RENEWABLE_ENERGY_SHARE's 2025 value
(7.02%) matches the energy page's own displayed "Key Indicator" figure (7.0%, rounded).
LOANS_TO_ECONOMY (~25.9-30.3 trillion KZT) is a plausible scale for Kazakhstan's total bank
credit stock.

**130/130 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — twelfth scale-up batch: 130 -> 133 indicators
Two new-territory research threads this batch, one abandoned and one that paid off
differently than intended.

**Abandoned: IMF GFS dataset.** Tried IMF's Government Finance Statistics dataflow
(IMF.STA:GFS_SOO) hoping for tax-type breakdowns (income/property/customs) to resolve the
long-standing individual-income-tax/property-tax/customs-duties gap. Unlike WEO's trivial
`{COUNTRY}.{CODE}` 2-key pattern, GFS has 8+ codelisted dimensions (SECTOR, GFS_GRP,
INDICATOR, INSTR_ASSET, GFS_STO, COFOG, etc.) with no simple wildcard query -- querying it
correctly would require substantial codelist research with real risk of guessing wrong
dimension values. Abandoned rather than fabricate a query.

**Minfin (3), a genuinely new fiscal scope found while chasing the same tax-breakdown
question:** discovered a "General government data ... (consolidated budget according to
IMF methodology)" document under Minfin's budget-document listing -- IMF GFS-methodology
general government (republican + local + social security funds combined), a BROADER scope
than every existing Minfin fiscal indicator (all republican-budget-only). Its own "Taxes"
row is a single aggregate too (no type breakdown, so the original question stays
unresolved), but the document itself is valuable: only one exists in the listing (unlike
GOV_DEBT's 23 snapshots), yet it already contains all 4 quarters of 2025 as separate
columns, so no historical backfill was needed. Connected: GG_TAXES, GG_SOCIAL_CONTRIBUTIONS,
GG_CASH_SURPLUS_DEFICIT. Values converted from the source's billion-KZT unit to million KZT.

**Sanity-checked before committing:** GG_TAXES summed across all 4 2025 quarters (~23.46
trillion KZT) exceeds TAX_REVENUE's republican-only 2025 annual figure (~14.46 trillion
KZT) -- the expected direction given the broader general-government scope. Documented
explicitly in both the fetcher and sources.yaml that these GG_* indicators should NOT be
expected to reconcile with the republican-budget-only indicators already connected.

**133/133 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — thirteenth scale-up batch: 133 -> 134 indicators
Finally opened the Minfin "Statistical bulletin" document (49 sheets, 1.5MB) that
earlier sessions had explicitly set aside as too large/risky to attempt -- it turned out
perfectly parseable, and resolved the batch's headline target: CUSTOMS_DUTIES.

**Minfin (1):** CUSTOMS_DUTIES, from sheet "табл 8 (дох)" -- the full KBK (budget
classification code) breakdown of republican-budget revenue by exact tax/fee type.
'Таможенные платежи' (class 06/subclass 1) is a genuine, distinct line.

**Structural finding, not a new indicator:** the SAME sheet definitively confirms
individual income tax and property tax do not exist anywhere in the republican budget --
only 'Корпоративный подоходный налог' (corporate income tax) appears under the income-tax
category. This is consistent with Kazakhstan's budget code assigning individual income tax
and property tax entirely to LOCAL government budgets, explaining why no republican-level
document (Dynamics file, General Government IMF-methodology file, or this one) ever
surfaced them across three separate sessions of searching. Not pursued further --
extracting them would mean aggregating 17+ separate local budget execution reports, a real
methodological undertaking distinct from what this project's fetchers do elsewhere, not a
search failure. Documented in sources.yaml so a future session doesn't re-search for them
at the republican level.

**Critical data-quality catch:** this document series' TITLES ("Statistical bulletin as of
{Month} 1, {YYYY}") are unreliable -- three documents all titled "as of April 1, 2026"
turned out, on actually opening their sheets, to cover three different periods (Jan-Feb,
Jan-Mar, Jan-May 2026). Built the fetcher to parse each document's own internal period
header text instead ("январь-май отчет 2026 г."), never trusting the title. The resulting
series is genuinely year-to-date cumulative (resets near zero every January) -- confirmed
monotonic within each of the 13 available documents' respective years, and documented
clearly so the expected sawtooth pattern across year boundaries isn't mistaken for a bug.

**134/134 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-30 — fourteenth scale-up batch: 134 -> 135 indicators
Resolved the last of the session's headline gaps: poverty. Confirmed absent from the
"Статистика уровня жизни" category's own RK-totals list in an earlier batch, and multiple
keyword phrasings ("уровень бедности", "черта бедности") had failed -- a more specific
phrase ("доходами ниже величины прожиточного минимума") found it.

**BNS (1):** POVERTY_HEADCOUNT (code 64410201, "Общая численность населения с доходами
ниже величины прожиточного минимума") -- confirmed genuine via the indicator's own
"Паспорт" page (household budget survey sourced, official BNS methodology cited), not a
fabricated proxy. Values initially looked implausibly low (~90,000-147,000 persons against
a ~20M population) compared to commonly-cited international poverty rates, but confirmed
correct: they match the indicator's own displayed chart exactly, and BNS's national
subsistence-minimum threshold (a specific, narrower definition than international poverty
lines) genuinely produces a low measured share.

**Deliberately NOT computed:** a population-SHARE (%) version of this indicator. No such
series exists on Taldau (only headcounts and a households-count variant were found);
dividing the headcount by POPULATION_BNS ourselves would have been a fabricated derived
ratio, against this project's established practice of only publishing what the source
agency itself computes and publishes.

**Found but not implemented:** "Величина прожиточного минимума" (the subsistence-minimum
threshold itself, KZT/month) -- its Taldau tree returns a hidden intermediate node
requiring genuine parent/child recursion, a different and deeper API interaction pattern
than the one-shot flat query every other Taldau indicator in this project uses. Left for a
future session with budget to build that capability rather than rushed in.

**135/135 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — fifteenth scale-up batch: 135 -> 139 indicators
Went back into the "Statistical bulletin" document (the one that resolved CUSTOMS_DUTIES
last batch) to explore its other 48 sheets, having proven it worth the effort. Sheet
"табл 10" -- republican budget expenditure by ECONOMIC classification (type of spending:
wages/capital/transfers/subsidies), a genuinely different dimension from the FUNCTIONAL
classification (health/education/defense) already covered by GOV_HEALTH_SPENDING etc.

**Minfin (4):** GOV_WAGES_EXPENDITURE, GOV_CAPITAL_EXPENDITURE, GOV_PENSIONS_EXPENDITURE,
GOV_SUBSIDIES_EXPENDITURE -- each a single, exact-name-matched row, confirmed present
exactly once across all 13 currently-listed bulletin documents. Refactored CUSTOMS_DUTIES's
implementation into a shared `_fetch_bulletin_row(sheet_name, row_matcher, indicator_id)`
helper (verified the refactor preserves identical output before wiring in the new
indicators) so all 5 bulletin-sourced indicators share the same period-parsing, multi-
document iteration, and year-to-date-cumulative documentation established last batch.

**Sanity-checked before committing:** all 4 new series are monotonic within each of the 13
documents' years, consistent with the same cumulative pattern as CUSTOMS_DUTIES.
GOV_CAPITAL_EXPENDITURE's very low January figure (~1bn KZT vs ~440bn by June) is plausible
rather than alarming -- capital projects conventionally front-load spending later in the
fiscal year. GOV_SUBSIDIES_EXPENDITURE is explicitly documented as NOT expected to
reconcile with BNS's separate national-accounts SUBSIDIES indicator (different agency,
different concept, different measurement approach).

**139/139 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.
