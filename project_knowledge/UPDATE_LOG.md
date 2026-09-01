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

## 2026-08-31 — sixteenth scale-up batch: 139 -> 140 indicators (small, disciplined)
Continued exploring the "Statistical bulletin" document's remaining sheets (табл 11, 13,
15, 16, 17, 18). This batch's headline is less about what was added and more about what
was deliberately NOT added, despite finding real candidate data.

**Minfin (1):** SUBVENTIONS_REPUBLICAN (sheet "табл 18", "Республикалық бюджеттен
субвенциялар") -- uses the SAME multi-year-annual-column layout as the small "Dynamics of
execution" file, so only the single most recent bulletin was needed (no 13-document
backfill), keeping this one low-risk despite coming from the same complex document as
CUSTOMS_DUTIES/GOV_*_EXPENDITURE.

**Investigated and explicitly declined:** "табл 13" (consolidated-budget execution report)
would have given a genuinely new CONSOLIDATED-level (all government levels + funds) budget
deficit measure -- a real, distinct fiscal indicator. Checked its structure across all 13
bulletin vintages and found the column layout (target name sometimes in column 1, sometimes
column 2) and row-label conventions (Roman-numeral prefixes present in some vintages,
absent in others) both vary in ways that risk silently landing on the wrong column or row
in some documents. This is the same category of risk that led to abandoning the IMF GFS
dataset earlier in the session -- rather than build fragile heuristics to paper over
inconsistent source structure, left it unconnected. Also re-confirmed from this table (a
third, independent document) that individual income tax and property tax remain absent even
at the broadest consolidated government level -- the local-budget-only conclusion from
CUSTOMS_DUTIES's batch stands.

Table 11 (local-budget economic classification, a mirror of табл 10) and table 17 (National
Fund portfolio composition, quarterly, USD-denominated) were also found and look genuinely
promising, but not pursued this batch given time already spent -- left for a future
session.

**140/140 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — seventeenth scale-up batch: 140 -> 144 indicators
Followed up on the two promising leads left unpursued at the end of the sixteenth batch:
табл 11 (local-budget economic classification) and табл 17 (National Fund portfolio
composition).

**Minfin (4):**
- LOCAL_GOV_WAGES_EXPENDITURE, LOCAL_GOV_CAPITAL_EXPENDITURE, LOCAL_GOV_SUBSIDIES_EXPENDITURE
  -- the direct local (regional) budget counterparts to GOV_WAGES_EXPENDITURE/GOV_CAPITAL_
  EXPENDITURE/GOV_SUBSIDIES_EXPENDITURE (табл 10, republican), sourced from sheet "таб 11"
  (confirmed the missing "л" is a stable Minfin typo across all 13 bulletin vintages, not
  edition-to-edition variance). Row labels each matched exactly once in all 13 vintages.
  NOTE: this local-budget sheet has no "Пенсии" (pensions) row at all -- pensions are not a
  local-budget expenditure category in Kazakhstan, so no LOCAL_GOV_PENSIONS_EXPENDITURE was
  added (not an oversight).
- NATIONAL_FUND_ASSETS -- total market value (USD) of the National Fund of Kazakhstan's
  investment portfolio, sourced from sheet "табл 17 кв+1мес" (name varies slightly across
  vintages -- "табл 17 кв" in the 2 oldest bulletins -- matched by prefix, not exact string).
  Structurally distinct from every other bulletin-sourced indicator so far: a point-in-time
  quarterly snapshot rather than a year-to-date cumulative flow, and denominated in USD, not
  KZT. Iterating across the 13 listed bulletins yielded 6 distinct quarter-end values
  (2024-Q4 through 2026-Q1, USD 57.9bn-63.9bn), each bulletin reporting whichever quarter had
  most recently closed as of its own publication. Originally sourced by Minfin FROM the
  National Bank RK per the sheet's own footer, republished in the Statistical Bulletin.

**144/144 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — eighteenth scale-up batch: 144 -> 148 indicators (with a caught duplicate)
Revisited табл 17 (the National Fund portfolio sheet used for the previous batch's
NATIONAL_FUND_ASSETS) to extract its sub-portfolio and asset-class breakdown, which had been
noted as present but not yet extracted.

**Important correction first:** while wiring up the new sub-portfolio rows, discovered that
NATIONAL_FUND_ASSETS (added in the seventeenth batch, minutes earlier) collides with an
ALREADY-EXISTING indicator of the exact same ID, sourced from NBK formId=34 (added in an
earlier session). Compared values: this sheet's 2026-Q1 total (USD 62,395,968,457) vs NBK's
2026-04-01 value (USD 62,395,954,208) -- a ~0.00002% difference, almost certainly the same
underlying valuation one day apart. The NBK series is also strictly better (monthly vs
quarterly frequency, longer history). **Removed** the duplicate minfin-sourced
NATIONAL_FUND_ASSETS entirely (indicators.yaml, update_minfin.py, sources.yaml, and the
fetcher function itself) rather than leaving two indicators with the same ID silently
colliding in indicator lookups and the unified dataset. Confirmed post-cleanup: zero
duplicate IDs across all 148 indicators, and the original NBK series (102 monthly rows,
untouched) still intact.

**Minfin (5, net +4 after the above removal):** NATIONAL_FUND_STABILIZATION_PORTFOLIO,
NATIONAL_FUND_SAVINGS_PORTFOLIO, NATIONAL_FUND_SAVINGS_BONDS, NATIONAL_FUND_EQUITIES,
NATIONAL_FUND_GOLD -- all from the same табл 17 sheet, genuinely new information NBK's own
formId=34 does not provide (only the grand total). Row order (Стабилизационный портфель /
Облигации / Деньги.../ Сберегательный портфель / Облигации / Акции / Золото / Балама
құралдар / Целевые талаптар / БАРЛЫҒЫ) confirmed byte-identical between the oldest (2024-Q4)
and newest (2026-Q1) bulletin vintages, 13 months apart. One genuine ambiguity handled: the
label "Облигации" (bonds) appears TWICE in the sheet -- once under the stabilization
portfolio (value consistently near-zero) and once under the savings portfolio (the real,
substantial figure, ~52-55% of savings). Resolved deterministically by ROW ORDER (take the
first "Облигации" row after the "Сберегательный портфель" header row), not by label text
alone -- verified live that this correctly grabs the substantial savings-portfolio figure
(USD 30.8-32.4bn across quarters) rather than the always-near-zero stabilization one.

**148/148 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — nineteenth scale-up batch: 148 -> 152 indicators
Explored the remaining unmapped sheets of the "Statistical bulletin" document (табл 15, 16,
19-29, 28), a mix of budget-execution, debt-servicing, procurement, and compliance tables not
yet touched in this session.

**Minfin (4):**
- GOV_ACCOUNTS_PAYABLE / GOV_ACCOUNTS_RECEIVABLE (sheets "табл 24 кв" / "табл 25 кв", state
  budget creditor/debtor arrears) -- same single-latest-document, multi-year-annual-column
  pattern as SUBVENTIONS_REPUBLICAN, now factored into a shared `_fetch_bulletin_annual_row`
  helper (SUBVENTIONS_REPUBLICAN refactored onto it too, output unchanged, re-verified live).
  GOV_ACCOUNTS_PAYABLE shows a striking ~3.4x rise from 2023 to 2025 (297.7bn -> 1,025.4bn
  million KZT) -- a genuine fiscal-health signal, not a data artifact (row label is an
  explicit "(1+2)" sum of the republican+local sub-rows above it).
- GOV_FINANCIAL_ASSETS_SOLD (sheet "табл 16", proceeds from selling state financial assets)
  -- year-to-date cumulative, 13-document backfill like CUSTOMS_DUTIES. One genuine wrinkle:
  the period phrasing differs between vintages (12 of 13 say "January-{end month}", the single
  oldest says just "{month}" with no range) -- handled with a regex that accepts either form
  rather than assuming the newer phrasing everywhere. The mirror row (new asset acquisitions)
  was consistently blank across all 13 vintages -- a real gap in the source, left unextracted
  rather than assumed to be always-zero.
- GOV_AUDIT_VIOLATIONS_AMOUNT (sheet "28 табл" -- note the reversed numbering, confirmed
  stable across all 13 vintages, not a typo) -- total amount of financial violations found by
  Minfin's own internal audit committee, a compliance/anti-corruption metric structurally
  unlike anything else connected so far. Confirmed genuinely YTD-cumulative (not point-in-
  time) by checking that values climb monotonically within each year before resetting in
  January. Uses an "as of {month} 1" Kazakh date convention unique to this sheet; only the 10
  month-name forms actually observed live are hardcoded -- the 2 unobserved ones (January, May)
  will safely skip rather than being guessed at if they ever appear.

**152/152 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — twentieth scale-up batch: 152 -> 156 indicators (with a caught date bug)
Explored the remaining previously-unlooked-at Statistical Bulletin sheets: табл 8 (расх)/9
(republican expenditure by departmental classification -- conceptually redundant with the
existing GOV_EXPENDITURE, not pursued), табл 26 (tax arrears), табл 27 (pension contribution
arrears), and табл 29 (state procurement).

**Important bug caught before committing:** the first implementation of TAX_ARREARS_TOTAL and
the two PENSION_CONTRIBUTIONS_* indicators stamped their records at year-end (Dec 31), reusing
_fetch_bulletin_annual_row's default date logic -- but these three sheets are explicitly "as of
January 1" point-in-time snapshots, not year-end annual reports, so every record was mislabeled
by up to 11 months. Caught by actually reading the test output's dates rather than just checking
record counts. Fixed by generalizing _fetch_bulletin_annual_row with a `date_for_year` override
(default preserves the existing Dec-31 behavior for every previously-shipped indicator) and
re-verified live that all three now stamp at YYYY-01-01. A reminder that "records extracted
successfully" and "records extracted correctly" are different checks -- worth eyeballing actual
values, not just counts, especially when introducing a new header/date convention.

**Minfin (4):**
- TAX_ARREARS_TOTAL (табл 26 пг) -- total overdue tax/payment debt owed to the republican
  budget by taxpayers, distinct from GOV_ACCOUNTS_RECEIVABLE (the budget's own settlement
  arrears). Matched by an EXACT (not substring) label match to avoid several subtotal rows in
  the same sheet that also contain "БАРЛЫҒЫ" as part of a longer compound label.
- PENSION_CONTRIBUTIONS_RECEIVED / PENSION_CONTRIBUTIONS_ARREARS (табл 27 пг) -- a genuine
  structural first: the same two years appear TWICE in this sheet's header (once for receipts,
  once for arrears), so the shared annual-row helper couldn't be reused directly; a bespoke
  fetcher partitions the 4 year-header matches into first-half (receipts) / second-half
  (arrears) by column order, verified live. Arrears are notably larger than receipts and
  growing faster -- a real pension-compliance signal.
- GOV_PROCUREMENT_TOTAL_VALUE (табл 29 пг) -- total value of concluded state procurement
  contracts. Structurally sparse: only published once a full calendar year closes (present in
  just 3 of 13 listed bulletins, covering 2 distinct years), so uses CUSTOMS_DUTIES-style
  multi-document iteration rather than the single-latest-document pattern. This sheet's value
  columns are in raw tenge, not million tenge like the rest of the document -- converted for
  consistency. A neighboring "savings/economy" column was left unextracted since its header
  states yet another, different unit within the same row -- flagged for a future, more careful
  pass rather than guessed at.

**156/156 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — twenty-first scale-up batch: 156 -> 161 indicators (resolves a long-standing gap)
Explored the remaining foundational Statistical Bulletin sheets (табл 1-7), left unlooked-at
since earlier passes focused on more specialized tables further into the document.

**Headline finding: individual income tax IS extractable after all.** Earlier this session
(and in prior sessions, per CUSTOMS_DUTIES's and SUBVENTIONS_REPUBLICAN's module comments),
individual income tax was investigated repeatedly and consistently found absent from every
REPUBLICAN-level document checked (the "Dynamics of execution" file, табл 8 (дох)) and even
the broadest CONSOLIDATED-government document (табл 13, ultimately not connected for unrelated
structural reasons) -- correctly concluded to be a genuinely local-budget-only tax under
Kazakhstan's budget code, and that conclusion was treated as closed. Opening табл 3
("Исполнение государственного бюджета" -- execution of the STATE budget, i.e. republican +
local combined, not just republican) this batch, individual income tax DOES appear there as a
real, distinct, non-zero line -- because it's collected at the local level but rolled up INTO
the state-level aggregate. This doesn't contradict the earlier research: cross-checked against
табл 7 ("Исполнение РЕСПУБЛИКАНСКОГО бюджета" specifically), no individual-income-tax row
appears there at all, confirming republican-level absence still holds. The lesson: "not found
in every document we checked" is not the same as "structurally absent everywhere" -- there was
still a STATE-level document not yet opened. Property tax was searched for in the same табл 3
breakdown and was NOT found itemized there either -- that specific question remains open.

**Minfin (5):**
- INDIVIDUAL_INCOME_TAX (табл 3) -- 1,992,384.85 (2023) to 2,859,192.36 (2025) million KZT.
- STATE_BUDGET_REVENUE / STATE_BUDGET_EXPENDITURE / STATE_BUDGET_DEFICIT /
  STATE_NON_OIL_DEFICIT (same sheet) -- broader-scope (republican + local combined) companions
  to the existing republican-only GOV_REVENUE/GOV_EXPENDITURE/BUDGET_DEFICIT/
  NON_OIL_BUDGET_DEFICIT, using the same multi-year-annual-column single-latest-document
  pattern established for SUBVENTIONS_REPUBLICAN.

**161/161 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — twenty-second scale-up batch: 161 -> 166 indicators (a shared-helper bug caught and fixed)
Followed up on the previous batch's discovery: табл 4 (STATE-level revenue KBK detail, the
state-budget counterpart to табл 8 (дох)) for the property-tax half of the individual-income-
tax question, and табл 6 (STATE-level economic classification) to complete the wages/capital/
subsidies trilogy already covered at republican and local level.

**Two real data-quality issues found and fixed in табл 4, neither guessed at:**
1. The Russian label for property tax ("Налоги на имущество") is unreliable -- several older
   bulletin vintages render it as "Hалоги на имущество" with a LATIN 'H' substituted for the
   Cyrillic 'Н', a genuine artifact in Minfin's own spreadsheet template. Confirmed by directly
   inspecting the raw string in a failing document rather than assuming a transcription error.
   Fixed by matching the KAZAKH label instead, which is byte-identical across all 13 vintages.
2. **A latent bug in the shared _fetch_bulletin_row helper**, discovered only because this
   sheet's row-padding happened to vary: the helper's "-2" value-column convention (used by
   every sheet since CUSTOMS_DUTIES) silently landed on a None padding cell in 4 of 13
   vintages, because this specific row's trailing-cell count genuinely differs between
   documents (7, 9, or 10 elements for the same logical row). The fetcher didn't error --
   it just quietly returned 9 records instead of 13, which only stood out because 13 was the
   expected count from prior sheets. Fixed by adding a `value_col` override to the shared
   helper (default -2 preserved, zero behavior change for every other already-shipped
   indicator -- explicitly re-verified live on CUSTOMS_DUTIES and STATE_GOV_WAGES_EXPENDITURE
   after the change). A reminder to keep checking record counts against expectations, not just
   "did it return something," even for indicators built on well-established shared helpers.

**Minfin (5):**
- PROPERTY_TAX / LAND_TAX (табл 4) -- resolves the property-tax half of the question left open
  by last batch's INDIVIDUAL_INCOME_TAX discovery.
- STATE_GOV_WAGES_EXPENDITURE / _CAPITAL_EXPENDITURE / _SUBSIDIES_EXPENDITURE (табл 6) --
  completes the republican/local/state trilogy alongside the existing GOV_*_EXPENDITURE and
  LOCAL_GOV_*_EXPENDITURE indicators.

**166/166 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — twenty-third scale-up batch: 166 -> 168 indicators (first new BNS pass this session)
User asked directly what's still missing for a comprehensive analysis of Kazakhstan's economy.
Answered by category breakdown of the current 166 indicators, and flagged migration and
trade-by-partner/commodity as the most realistic gaps to close within the existing 4 sources
(BNS/NBK/Minfin/IMF), as opposed to genuinely out-of-scope items (oil/gas production volumes,
which live with KMG/the energy ministry, not these 4 statistical agencies).

Checked trade-by-partner first: downloaded and inspected the actual EXPORTS/IMPORTS source
files (56MB/93MB XLSX) already used for the existing totals -- confirmed they break down by
HS/TNVED commodity code and by Kazakhstan REGION, but NOT by partner country. Trade-by-partner
would need a genuinely different, not-yet-located BNS dataset -- left unpursued rather than
searched further this batch.

**BNS (2), the first new BNS indicators added this session (every prior batch was Minfin):**
MIGRATION_ARRIVALS / MIGRATION_DEPARTURES -- found via Taldau's keyword search ("миграция"),
which returned 21 related indicators (internal migration; CIS/non-CIS partner breakdown;
demographic breakdowns by marital status/education/occupation); picked the "all flows" totals
as the clean headline pair over the more granular variants. Classified across 4 dictionaries,
cracked via the same live-ExtJS-component-tree technique established for AVG_WAGE/RETAIL_TRADE/
CONSTRUCTION/POVERTY_HEADCOUNT (Claude Browser tool, reading the page's own already-loaded grid
component's live request params rather than guessing). Verified live, then cross-checked against
known history: 2000 shows 155,749 departures vs only 47,442 arrivals -- a large net outflow
consistent with Kazakhstan's well-documented post-Soviet emigration wave -- reversing to a net
inflow by 2025 (23,761 arrivals vs 7,608 departures).

**168/168 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — twenty-fourth scale-up batch: 168 -> 169 indicators (a latent date bug fixed pre-emptively)
Continued the BNS/Taldau research from the previous batch. Checked several candidate gaps via
keyword search: non-resource ("несырьевой") export share/value (found, but data stops at 2019
-- stale, not pursued), a narrow ICT-hiring-difficulty survey metric (not a general labor-market
indicator, skipped), and a manufacturing export/import combined index (needs multi-dimensional
classification, not pursued this batch).

**BNS (1):** LABOR_PRODUCTIVITY (code 111216) -- worked with the default single-dimension
params, unusual for Taldau indicators this session (most need live-ExtJS-tree parameter
recovery). 26 fresh annual values through 2025.

**A real latent bug found and fixed while investigating, before it could ship wrong data:**
found a housing price index (code 261605, "Индексы цен на рынке жилья") that turned out to be
QUARTERLY (period_id=5), not annual like every other Taldau indicator connected so far. Testing
it exposed that `_fetch_taldau_annual_index`'s date-stamping always assumed year-end (Dec 31)
regardless of what period the response's own data keys actually represented -- for a quarterly
index this would have silently collapsed all 4 quarters of a year into duplicate December-31
records, corrupting the series. Decided NOT to add the housing index itself (its own displayed
period range on BNS's site ends at Q4 2020 -- discontinued/stale, not a fetcher problem), but
fixed the underlying bug anyway since it would bite the next quarterly index someone connects:
the response's 'yMMYYYY' keys already carry the true month, so the fix parses that directly
into a proper quarter-end (or year-end) date instead of assuming year-end. Re-verified live
against GDP_REAL to confirm zero behavior change for every already-shipped annual indicator.

**169/169 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — twenty-fifth scale-up batch: 169 -> 171 indicators (closes two long-flagged gaps)
Self-directed batch: checked the existing indicator set for FDI (foreign direct investment)
coverage and confirmed a real gap -- only domestic fixed-capital INVESTMENT existed, no
cross-border investment flow. Explored NBK's full category tree via GET
/api/v1/data/categories (a much richer structure than any single form browsed before) and
found both FDI and a genuine answer to the long-standing "no aggregate found in NBK forms
16/17/430" government-securities gap.

**A real scare, investigated and ruled out before it cost anything:** while designing the
pagination for these two new fetchers, noticed page=0 and page=1 appeared to return byte-
identical content in a quick small-pageSize test -- raising the alarming possibility that
EVERY existing NBK indicator using the established page-loop pattern (M2, M3, FX_RESERVES,
EXTERNAL_DEBT, etc.) might be silently missing its most recent data, since a full-page
duplicate would make the loop's "stop when we've fetched totalRows" check trigger too early.
Verified properly at production pageSize (500) before concluding anything: page=0 and page=1
are NOT duplicates at real page size -- adjacent pages simply share one overlapping boundary
row (harmless), and the small-pageSize test that suggested otherwise was a coincidence of tiny
sample size. No existing indicator was affected; this was confirmed, not assumed, before
moving on.

**NBK (2):**
- FDI_NET_INFLOW -- net foreign direct investment inflow to Kazakhstan, BPM6 directional
  principle, found in NBK's balance-of-payments category among ~20 sibling FDI series (gross/
  net, by country, by sector); picked the standard aggregate over the breakdowns. 85 quarterly
  points, 2005-2026, genuinely volatile including negative (net-disinvestment) quarters.
- GOV_SECURITIES_MEUKAM -- re-investigated the government-securities gap and confirmed the
  earlier "no aggregate" conclusion still holds (checked all 14 instrument-type values in the
  source, genuinely no "Total" row) -- rather than fabricate a sum ourselves, connected only
  the single largest component (МЕUКАМ, medium/long-term treasury bonds, ~22.4 trillion KZT,
  an order of magnitude larger than everything else combined), labeled precisely as that one
  instrument rather than overstated as "the market."

**171/171 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — twenty-sixth scale-up batch: 171 -> 175 indicators
User asked for a broad ~50-100 candidate list for a comprehensive economic analysis; responded
with a categorized backlog (prices, labor detail, business demography, external sector, financial
sector, tourism, ICT, demographics/social, energy, NBK survey results), honestly caveated that not
all would pan out. This batch worked the external-sector portion of that list.

Refactored FDI_NET_INFLOW/GOV_SECURITIES_MEUKAM's duplicated pagination loops into a shared
`_fetch_nbk_form_paginated` helper (re-verified both indicators identical post-refactor) before
adding new NBK forms on top of it -- same "factor out on the 3rd+ use" discipline applied
throughout this session.

**NBK (4):**
- IIP_NET / IIP_ASSETS / IIP_LIABILITIES (formId=309, "International Investment Position:
  standard presentation") -- found among ~16 classification dimensions by filtering for the
  three completely UNCLASSIFIED headline rows per period. Cross-checked internal consistency
  (Assets - Liabilities = Net to the cent for multiple quarters) before trusting the discovery.
  22 quarterly points, 2021-2026, USD million.
- CURRENT_ACCOUNT_BALANCE (formId=324, "Current account of the balance of payments") -- same
  unclassified-headline-row pattern, was literally the first row returned by the API. 24
  quarterly points, 2020-2026, USD million, recently in deficit (plausible for Kazakhstan given
  FDI-related income outflows).

**175/175 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — twenty-seventh scale-up batch: 175 -> 178 indicators (financial sector)
Continued working the candidate backlog from the earlier ~50-100 list: financial-sector
indicators (bank profitability, pension fund assets).

**NBK (3):**
- BANK_ROA / BANK_ROE (formId=314, same Financial Soundness Indicators form as
  CAPITAL_ADEQUACY_RATIO/NPL_RATIO) -- checked the form's other ~35 `indicator` values and
  found two more clean single-valued series. Also explicitly investigated and declined two
  more from the same list: "Total assets" has three distinct values per date with no visible
  disambiguating field (a genuine unresolved source ambiguity, not guessed at), and
  "Residential real estate prices (% change/12mo)" is exactly 0.0 for all 18 periods -- an
  unreported placeholder, not real data.
- PENSION_FUND_ASSETS (formId=25) -- total pension savings held by Kazakhstan's Unified
  Accumulative Pension Fund (UAPF/ЕНПФ). Most rows in this form are flow data (contributions,
  payouts, fees); the total stock figure was found as the one row per month with every
  sub-classification field empty. 43 monthly points, 2023-2026, 27.07 trillion KZT as of
  2026-08 -- a plausible scale for Kazakhstan's largest institutional investor.

**178/178 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — twenty-eighth scale-up batch: 178 -> 180 indicators (insurance premiums)
Continued working the candidate backlog: insurance-sector indicators.

**NBK (2):**
- INSURANCE_PREMIUMS_GENERAL / INSURANCE_PREMIUMS_LIFE (formId=132, "Total statement on
  insurance premiums of insurance (reinsurance) organizations") -- matched rows where
  `pnl_subtype` = "Insurance premiums accepted under insurance contracts",
  `insurance_type` = "Total", `insurance_org_type` in {General, Life}, and no residency
  breakdown applied. 31 monthly points each, 2023-02 to 2026-07, YTD-cumulative KZT
  (confirmed cumulative by inspecting the within-year value pattern), converted
  thousand -> million KZT. The form has no combined General+Life total row -- connected
  both organization types separately rather than fabricate a sum, per the project's
  standing no-fabricated-aggregates rule.
- Also inspected formId=450 ("Main financial indicators of the insurance market") as a
  candidate for claims/other insurance metrics; declined for now -- no clear
  indicator-name field to key off safely without guessing row semantics.
- Refactored `_fetch_iip_row`-style page loop usage; both new fetchers reuse the shared
  `_fetch_nbk_form_paginated` helper directly (no new pagination code written).

**Pipeline note:** the first full-pipeline verification run for this batch returned exit
code 4 with no captured output (likely a transient issue with the background task
runner or a momentary network blip on one of the ~180 live source fetches). Re-ran
immediately in the foreground: completed cleanly, exit code 0, all 180/180 indicators
`ok` in the run log, 29/29 tests passing. Treated as a one-off transient failure, not a
regression -- both new fetchers were independently verified correct before and after.

**180/180 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — twenty-ninth scale-up batch: 180 -> 182 indicators (pensions + reserve adequacy)
Continued working the candidate backlog: explored the rest of NBK's category tree
(`GET /api/v1/data/categories`) beyond formIds already used, and found two more clean
indicators plus two more confirmed declines.

**NBK (2):**
- PENSION_PAYMENTS (formId=29, "Information on the volume of pension savings...") --
  total pension savings payments made from UAPF/ЕНПФ. The unclassified top-level total
  row (`class_type='Pension savings payments'`, `row_code='Pension savings payments'`)
  is duplicated across `type` values (thsd. tenge / Units for headcount / Units for
  transaction count) at the exact same row_code+class_type -- filtering on
  `type='thsd. tenge'` was required to land on exactly one row per date. 44 monthly
  points, 2023-01 to 2026-08, YTD-cumulative KZT.
- RESERVES_IMPORT_COVER (formId=469, "The indicators of the adequacy of the
  international reserves...") -- months of import cover provided by Kazakhstan's
  reserves. A small, clean 5-indicator form. 50 quarterly points, 2014-Q1 to 2026-Q2,
  smooth and continuous throughout.

**Declined (2), both confirmed by direct inspection, not guessed:**
- INSURANCE_CLAIMS (formId=133) -- the natural pairing with last batch's premiums
  indicators. Unlike premiums, the net-claims-expense rows have no `insurance_type`
  ='Total' value, only Compulsory/Voluntary-personal/Voluntary-property sub-totals with
  no published combined figure. Summing them ourselves would fabricate an aggregate the
  source doesn't publish.
- RESERVES_GUIDOTTI_RATIO and the same form's other two percent-denominated indicators
  (formId=469) -- found a genuine, CURRENT source-side structural break: starting
  exactly the 2026-01-01 report, all three percent-type series drop ~100x in magnitude
  while still labeled `value_type1='percent'` (e.g. Guidotti ratio: 135.9 -> 1.495
  between 2025-10-01 and 2026-01-01), and one of them's `indicator` label field is
  missing entirely from those two dates onward. The unaffected "months of import cover"
  series (RESERVES_IMPORT_COVER, connected above) shows no break across the same
  dates, ruling out a fetcher bug -- this is a live problem in NBK's own published data.
  Reconciling it would require guessing whether to rescale old or new values, which the
  MASTER TASK rules forbid. Declined.

**182/182 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — thirtieth scale-up batch: 182 -> 186 indicators (enterprise survey) + faster verification
First pass through NBK's "Survey Results" -> "Enterprise Monitoring" category, which had
been flagged as unexplored since the earlier gap analysis.

**NBK (4):** the quarterly business-tendency survey breaks each diffusion index down by
`industry`, but also publishes a genuine economy-wide `industry`='All sectors' aggregate
row — the source's own aggregate, so no fabrication was needed. Diffusion index runs
0-100 with 50 neutral (>50 expansion), the standard PMI-style convention, confirmed here
by the actual/expectations pairing and the values oscillating around 50.
- PRODUCTION_VOLUME_DIFFUSION_INDEX / PRODUCTION_EXPECTATIONS_DIFFUSION_INDEX
  (formId=365) — 42 quarterly points each, 2016-Q2 to 2026-Q3.
- DEMAND_DIFFUSION_INDEX / DEMAND_EXPECTATIONS_DIFFUSION_INDEX (formId=366) — 86
  quarterly points each, 2005-Q2 to 2026-Q3, the longest history found in any NBK survey
  form so far.

**Tooling: `scripts/update_agency.py` added.** Per-batch verification had been running
`update_all.py`, which re-fetches all 186 indicators from all four agencies (~20 min,
dominated by the Minfin XLSX bulletin downloads) even when a batch only touches one
agency's fetchers. The new script runs just the named agency updater(s), then rebuilds
the unified dataset and runs the tests exactly as `update_all.py` does — the unified
rebuild stays correct because it reads `data/processed/`, where the untouched agencies'
CSVs persist from the previous full run. Verified on this batch: 3m37s instead of ~20
min, and the rebuilt unified dataset was confirmed to still carry all 186 indicators
across all four agencies (imf/nbk/bns/minfin), not just the re-fetched NBK ones. This is
a verification shortcut only — `update_all.py` remains the production/scheduled path,
since only a full run refreshes every agency's data.

**186/186 confirmed indicators connected end-to-end** (43/43 NBK re-verified live this
run; other agencies unchanged since the 182/182 full run earlier today).
`pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — thirty-first scale-up batch: 186 -> 205 indicators (rest of Enterprise Monitoring)
Swept the remaining NBK Enterprise Monitoring forms in one pass, probing ten forms
concurrently rather than one at a time. Every series below reuses the same
`_fetch_enterprise_survey_index` helper (industry='All sectors' + indicator_code) added
last batch, so this was 19 new indicators with no new fetching logic.

**Verification tightened.** For each candidate the point count was checked to EXACTLY
equal the number of calendar quarters in its own date range (42 for 2016-Q2..2026-Q3, 86
for 2005-Q2..2026-Q3, 26 for 2020-Q2..2026-Q3) — a stronger check than "no duplicate
dates", which would pass a series with gaps.

**NBK (19):**
- Prices/inflation pressure: RAW_MATERIALS_PRICE_* and FINISHED_GOODS_PRICE_* (actual +
  expectations, 86 quarters back to 2005-Q2) — cost-push and output-price gauges;
  FINISHED_GOODS_PRICE_EXPECTATIONS is the firm-side counterpart to the household-side
  INFLATION_EXPECTATIONS. IMPORT_PRICE_* (actual + expectations) for imported inflation.
- Activity: CAPACITY_UTILIZATION (weighted-average % of capacity in use — a standard
  output-gap/slack measure), INVENTORIES_* (actual + expectations).
- Credit conditions: LOAN_RATE_ACCEPTABLE_KZT/FX and LOAN_TERM_ACCEPTABLE_KZT/FX — the
  rate and maturity enterprises report as acceptable for borrowing (a willingness
  measure, to be read against the actual LENDING_RATE, not as a market rate).
- Corporate stress: OVERDUE_ACCOUNTS_PAYABLE_SHARE, OVERDUE_ACCOUNTS_RECEIVABLE_SHARE,
  OVERDUE_BANK_LOANS_SHARE (the survey-side counterpart to the banking sector's
  NPL_RATIO), ENTERPRISE_DEBT_BURDEN.
- Trade participation: EXPORTERS_SHARE, IMPORTERS_SHARE.

**Declined (1):** formId=360 "Change in average wage" — every row is labeled
`period='quarter'`, but printing the actual dates showed the series is SEMI-ANNUAL
(Apr/Oct for actual, Jan/Jul for expectations), switching to consecutive quarters only in
2026. Labeling a mid-series frequency change as "quarterly" would mislabel the data, and
there is no single honest frequency for it, so it is left unconnected. Caught by not
trusting the row's own `period` field.

**205/205 confirmed indicators connected end-to-end** (62/62 NBK re-verified live via
`scripts/update_agency.py nbk` in 4m01s; unified dataset confirmed to still carry all 205
across imf/nbk/bns/minfin). `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — thirty-second scale-up batch: 205 -> 226 indicators (credit, deposits, payments, external debt)
**Discovery method changed.** Instead of reading one form at a time, wrote a structural
probe that fetches a form in full, groups every row by its complete classification
signature, and reports only the groups that form exactly one row per report_date across
the whole history. That turns "read the form and guess which row is the headline" into a
mechanical check, and it surfaced far more usable series per form than manual reading had.

**New shared fetcher `_fetch_nbk_exact_row(form_id, match, ...)`.** `match` pins every
classification field that must be set; a row qualifies only if it matches all of them AND
has no other classification field set, so a row carrying an extra breakdown dimension can
never be mistaken for the headline figure. It then asserts exactly one row per date — which
is itself the structural-change guard: a new upstream breakdown dimension raises
`StructuralChangeError` rather than silently returning one arbitrary sub-row of several.

**Real source defect found and handled honestly.** During verification four of the six
loan series failed while two identical-shaped ones passed. Cause, confirmed by fetching
formId=445 twice and diffing: the NBK API returns the SAME field with DIFFERENT CASING
between otherwise identical requests — `period` came back as both `'month'` and `'Month'`.
Some forms also pad labels (formId=340 reports `type` as `' mln USD'`, leading space). So
exact-string pinning is fragile for reasons that have nothing to do with the data. The
helper now compares values case-insensitively and whitespace-stripped; only presentation
differs, the classification is identical. This was diagnosed by reproducing the difference,
not by loosening the match until it passed.

**NBK (21):**
- Credit by borrower and currency (formId=445, 43 monthly pts from 2022-01):
  LOANS_BUSINESS_KZT/FX, LOANS_INDIVIDUALS_KZT/FX, and the non-bank
  LOANS_MICROFINANCE_INDIVIDUALS/BUSINESS — gives both the household-vs-corporate split and
  the corporate side of credit dollarization.
- Household deposits by currency and type (formId=261, 43 monthly pts from 2023-01):
  HOUSEHOLD_DEPOSITS_{FIXED_TERM,DEMAND,SAVING}_{KZT,FX} — the standard deposit
  dollarization pairs.
- Payment system value (formId=419, 71 monthly pts from 2020-01): PAYMENTS_TOTAL_VALUE,
  CASHLESS_PAYMENTS_VALUE, CASH_WITHDRAWALS_VALUE, PAYMENT_CARDS_VALUE — the KZT-value
  counterpart to the existing NON_CASH_PAYMENTS_SHARE.
- External debt maturity split (formId=340, 47 quarterly pts from 2014-Q4):
  EXTERNAL_DEBT_LONG_TERM/SHORT_TERM (159.2 + 23.6 = 182.8 bn USD, consistent with the
  known level), plus PRIVATE_EXTERNAL_DEBT_INTERCOMPANY (87.2 bn — the dominant component,
  largely oil-sector parent-to-subsidiary financing rather than market borrowing) and
  PRIVATE_EXTERNAL_DEBT_BANKS_OTHER_LT.
- GOLD_BULLION_SALES (formId=476, 36 quarterly pts from 2017-Q3) — retail gold demand.

**226/226 confirmed indicators connected end-to-end** (83/83 NBK re-verified live in
4m20s; unified dataset confirmed to carry all 226 across imf/nbk/bns/minfin).
`pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — thirty-third scale-up batch: 226 -> 237 indicators (remittance & external-debt composition)
Second sweep with the structural probe, over ten more NBK forms.

**NBK (11):**
- Remittance currency composition (formId=411, 58 monthly pts from 2021-09):
  REMITTANCES_{SENT,RECEIVED}_{USD,KZT,RUB} — the currency breakdown behind the existing
  REMITTANCES_SENT/RECEIVED totals. Notable in the current data: tenge-denominated
  outbound transfers (38.1 bn KZT) now exceed USD-denominated ones (20.0 bn).
- External debt by sector and instrument (formId=293, 26 quarterly pts from 2020-Q1):
  EXTERNAL_DEBT_GOV_LOANS_LT, EXTERNAL_DEBT_BANKS_LOANS_LT,
  EXTERNAL_DEBT_BANKS_SECURITIES_LT, EXTERNAL_DEBT_OTHER_SECURITIES_LT — complements last
  batch's maturity split with the who-owes-what-instrument dimension.
- GOV_SECURITIES_SECONDARY_NBK_NOTES (formId=16, 44 monthly pts from 2023-01) — secondary
  market turnover in NBK Notes, a liquidity measure distinct from the outstanding stock.

**Considered and skipped** (documented so the next sweep doesn't re-litigate them):
formId=408 (remittances by transfer system) would largely duplicate the existing
REMITTANCES_SENT/RECEIVED totals and contains unlabeled non-'Total' rows whose meaning is
not stated; formId=22 (UAPF portfolio structure) only exposes per-manager shares, not a
portfolio-wide allocation; formId=32 and 283 are per-company rather than economy-wide;
formId=486 (loan interest rates, 331 dates back to 1997) yielded no clean one-row-per-date
series under the probe and needs its own structural pass rather than a guess.

**237/237 confirmed indicators connected end-to-end** (94/94 NBK re-verified live in
4m23s; unified dataset confirmed to carry all 237). `pytest tests/ -q` — 29/29 passing.

## 2026-08-31 — thirty-fourth batch: unit-label bug FIXED, plus tourism (237 -> 247)

### Corrected a shipped mislabeling: six BNS series were declared "million KZT" but hold KZT
Found while checking units before adding new BNS indicators, not by chance. GFCF's stored
value is 3.92e13; read as "million KZT" that implies 3.9e19 KZT, which is impossible
(Kazakhstan's GDP is ~1.5e14 KZT). Read as plain KZT it is 39.2 trillion — the right order
of magnitude for Kazakhstan's gross fixed capital formation.

The decisive evidence was internal to the repo: BNS indicators added later already use
`unit: "KZT"` and sit at the SAME magnitude — GDP_INCOME_METHOD 159.6 trillion labeled
"KZT" next to HOUSEHOLD_CONSUMPTION 88.2 trillion labeled "million KZT". Same scale, two
different labels; the later convention is the correct one, because Taldau publishes these
in KZT.

Corrected to `unit: "KZT"` (values untouched, since the values were never wrong — only the
label was): **GDP_NOMINAL, INVESTMENT, GFCF, NET_EXPORTS, HOUSEHOLD_CONSUMPTION,
COMPENSATION_EMPLOYEES**. Anyone who had compared BNS GDP_NOMINAL against NBK M3 using the
declared units would have been off by a factor of 1,000,000. Re-ran the BNS pipeline so the
fix propagated into `metadata/` and the unified dataset — verified in
`data/unified/macro_long.csv` that all six now carry `unit=KZT`, matching GDP_INCOME_METHOD.

### Automated Taldau (BNS) discovery
Built the BNS counterpart to the NBK structural probe: search Taldau's own API
(POST `/ru/Search/getSearchPageGridData`) for candidate indexIds, then trial-fetch each with
the project's default national params to see which resolve. Note the search endpoint returns
HTTP 500 for a bare `keyword` body — it needs `page`/`start`/`limit` too, which is why
earlier sessions found "no generic search API". Indexes returning HTTP 500 on the trial
fetch are reported separately: those are multi-dictionary indexes needing real params
captured from a live page, NOT missing data.

### BNS (10) — first tourism indicators, from BNS's Tourism Satellite Account
TOURISM_VALUE_ADDED (1.42 trillion KZT) and TOURISM_GDP_SHARE (1% of GDP);
TOURISM_EMPLOYMENT (613,802 persons) and TOURISM_EMPLOYMENT_SHARE (6.7% of all employed);
TOURISM_INBOUND_CONSUMPTION (1.32 trillion KZT, the tourism-export side) and
TOURISM_OUTBOUND_CONSUMPTION (1.90 trillion KZT, the import side — Kazakhstan is a net
outbound-tourism spender); and the trip/night counts TOURISM_INBOUND_TRIPS,
TOURISM_DOMESTIC_TRIPS, TOURISM_OUTBOUND_TRIPS, TOURISM_INBOUND_NIGHTS (published only from
2020, so these are deliberately short series).

Several tourism parent aggregates were **skipped as implausible**: Taldau reports code
115301 "Промежуточное потребление в сфере туризма" as 79.2 trillion KZT while its own
sub-item is 3.36 trillion, and 115701 as 33.0 trillion against a 1.65 trillion sub-item.
Those parents cannot both be right and are not internally consistent, so they were left
unconnected rather than published with a guess about which reading is intended.

**247/247 confirmed indicators connected end-to-end** (68/68 BNS re-verified live in 53s).
`pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — thirty-fifth batch: life expectancy (247 -> 248), plus a full four-agency run
Ran `update_all.py` across all four agencies for the first time since the per-agency
verification shortcut was introduced: **247/247 ok, exit code 0**. That confirms the
shortcut had not been hiding anything — BNS, NBK, Minfin and IMF all still work together,
and the corrected KZT unit labels propagated correctly.

**BNS (1): LIFE_EXPECTANCY** (Taldau indexId 703906, code 614101), 25 annual points
2000-2024. This is a multi-dictionary index (region 67, locality type 64, sex 576) that
returns HTTP 500 under the default params, so its real params were captured from the live
page's own ExtJS store and then re-verified with a plain stateless request.

**Unit caveat, verified rather than assumed.** The source returns this series under
`measure_id=154`, and those values are MONTHS, not years — 905.28 for 2024, not 75.4.
Confirmation is independent of any assumption: dividing by 12 reproduces Kazakhstan's
published life expectancy across the entire series *including the COVID dip* — 65.45
(2000), 72.41 (2016), 71.37 (2020), 75.44 (2024). A wrong scale factor would not reproduce
that shape. The values are stored exactly as the source returns them, in months, with the
unit label stating so and the note giving the /12 conversion; they are deliberately NOT
silently divided, since the division is our inference and the months figure is the
source's actual output.

**Note for the next BNS sweep:** most remaining BNS gaps (fertility, birth/death rates,
ICT household access, R&D, crime, environment) are multi-dictionary indexes that return
HTTP 500 on the default params. They are not missing data — each needs one live-page param
capture, exactly as done here. The Taldau probe already lists them separately from genuine
misses, so the work is enumerated rather than open-ended.

**248/248 confirmed indicators connected end-to-end.** `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — thirty-sixth batch: FX market and non-bank financial sector (248 -> 258)
Started a systematic sweep of every NBK form not yet used. Enumerated them by diffing the
API's own category tree (239 forms) against the form ids referenced in
`scripts/fetchers/nbk.py` (42 in use), leaving 197 to probe — so remaining coverage is now
an enumerated list rather than guesswork.

**NBK (10):**
- OTC foreign exchange market (formId=41, 44 monthly pts from 2023-01):
  EXCHANGE_RATE_EUR_OTC, EXCHANGE_RATE_RUB_OTC, EXCHANGE_RATE_USD_OTC and the matching
  turnover series FX_OTC_VOLUME_{USD,EUR,RUB}. This fills a real gap — until now the only
  exchange rate in the dataset was the official USD/KZT rate, with no EUR or RUB at all.
  These are market bid rates, a different concept from the official rate, and are labeled
  as such so they are not mistaken for it.
- Other financial corporations (formId=26, 15 quarterly pts from 2023-01):
  OFC_NET_FOREIGN_ASSETS, OFC_CLAIMS_ON_NONRESIDENTS, OFC_LIABILITIES_TO_NONRESIDENTS,
  OFC_CLAIMS_ON_BANKING_SYSTEM — the non-bank financial sector (pension fund, insurers,
  brokers). Internal cross-check passed exactly: claims 12,029,184 − liabilities 3,308,881
  = net 8,720,303 million KZT.

**Self-inflicted failure worth recording.** The first verification run of this batch failed
with 69 errors — a `ConnectionResetError` followed by cascading DNS `NameResolutionError`s.
Cause was mine, not the source's: a 6-worker form probe was left running in the background
against the same host while the pipeline fetched. Nothing was corrupted, and the pipeline
behaved exactly as designed — it errored loudly and **refused to rebuild the unified
dataset**, rather than writing a partial one. Re-ran with nothing else touching the API:
104/104 ok. Lesson for future sweeps: never run the probe concurrently with a pipeline run.

**258/258 confirmed indicators connected end-to-end** (104/104 NBK re-verified live in
6m14s). `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — thirty-seventh batch: full external-debt decomposition (258 -> 273)
**Selection heuristic that worked.** The probe's second sweep flagged 47 forms with clean
series, but most are per-country / per-region / per-activity breakdowns that would add
hundreds of granular series. Sorting instead by *how few* clean series a form has turned
out to identify the headline forms precisely: formIds 348/349/350/351 have only 5-8 each,
which is the signature of a top-level breakdown rather than a long tail.

**NBK (15)** — Kazakhstan's gross external debt, now decomposed three independent ways:
- By resident sector (formId=349): EXTERNAL_DEBT_GENERAL_GOVERNMENT, _CENTRAL_BANK,
  _BANKS, _OTHER_SECTORS, plus EXTERNAL_DEBT_EX_INTERCOMPANY — the market-borrowing
  measure, which matters here because intercompany lending dominates the headline figure
  (largely oil-sector parent-to-subsidiary financing rather than real market debt).
- By government participation (formId=350): EXTERNAL_DEBT_PUBLIC_SECTOR,
  _PRIVATE_SECTOR, _GOV_GUARANTEED.
- By financial instrument (formId=351): EXTERNAL_DEBT_LOANS, _DEBT_SECURITIES,
  _TRADE_CREDITS, _CURRENCY_DEPOSITS, _SDR, _OTHER_LIABILITIES.
- Rollover risk (formId=348): EXTERNAL_DEBT_DUE_WITHIN_YEAR — debt due within a year on a
  *remaining*-maturity basis (43.0 bn USD), deliberately distinct from the existing
  EXTERNAL_DEBT_SHORT_TERM, which is on an *original*-maturity basis (23.6 bn USD).

All 49 quarterly points each, 2014-Q2 to 2026-Q2.

**The total row was deliberately not re-added.** It is already held as EXTERNAL_DEBT, and
was checked to be identical (182,778.238991 mln USD at 2026-04-01) rather than assumed to
be.

**Three independent arithmetic cross-checks, all exact to the cent** — computed from the
actually-fetched series, not from the source's presentation:
- sector split: 16,541.49 + 2,381.79 + 19,152.14 + 57,324.44 = 95,399.86 = EX_INTERCOMPANY
- public + private = 182,778.24 = EXTERNAL_DEBT
- six instrument categories = 182,778.24 = EXTERNAL_DEBT

Each difference came out to 0.0000, which is strong evidence the right rows were matched.

**273/273 confirmed indicators connected end-to-end** (119/119 NBK re-verified live in
6m20s). `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — thirty-eighth batch: external buffers and the financial account (273 -> 280)
Final probe sweep over the last 87 unused NBK forms, completing the enumeration of all 239
forms in the API's category tree.

**A label-alignment check that changed the outcome.** Two sibling forms looked equally
attractive — 484 (current account, comparative) and 485 (financial account, comparative),
both 85 quarterly points back to 2005. Before using either, their `code` labels were tested
against values:
- **485 PASSED** — two independent exact matches against already-shipped indicators: its
  "Reserve assets in months of import" equals RESERVES_IMPORT_COVER to the digit
  (9.752253), and its "Reserve assets, end of period" equals formId=469's reserve level
  exactly (66,786.22 mln USD).
- **484 FAILED** — its row labelled "Import of goods and services" carries 32.64 while the
  row labelled "in % of GDP1" for the same Debit/Goods-and-services cell carries 18,511.96.
  The percent and USD-million figures are swapped relative to their labels. Using it would
  mean guessing which label belongs to which value, so it was declined and documented.

That 485 passed the same test 484 failed is what makes this a source defect in 484 rather
than a misreading of the API.

**NBK (7), all 85 quarterly points from 2005-Q2:**
- RESERVES_AND_NATIONAL_FUND (128.6 bn USD) — NBK reserve assets plus National Fund foreign
  assets, Kazakhstan's total external buffer. Deliberately distinct from the existing
  monthly FX_RESERVES (NBK only) and NATIONAL_FUND_ASSETS (fund only); the levels of those
  two were NOT re-added from this form, only the combined figure and the ratios.
- RESERVES_AND_NF_IMPORT_COVER (18.8 months) — broader than RESERVES_IMPORT_COVER (9.8
  months), which counts NBK reserves only.
- RESERVES_AND_NF_GDP_SHARE, NATIONAL_FUND_GDP_SHARE, RESERVE_ASSETS_GDP_SHARE.
- FINANCIAL_ACCOUNT_BALANCE — the direct counterpart to CURRENT_ACCOUNT_BALANCE, which the
  dataset had been missing.
- BOP_OVERALL_BALANCE_GDP_SHARE.

**A generator guard that caught a real ambiguity.** The fetchers' match dicts were pulled
programmatically out of the probe results (rather than retyped) and asserted to reproduce
the exact values seen. That assertion fired: selecting on investment type "National Fund"
by substring also matched "Reserve assets and National Fund", so two different series
qualified. Fixed by requiring an exact field match — the wrong series would otherwise have
been silently published under the National Fund name.

**280/280 confirmed indicators connected end-to-end** (126/126 NBK re-verified live in
6m32s). `pytest tests/ -q` — 29/29 passing.

### NBK form coverage closed out (scope decision, 2026-09-01)
The NBK sweep is finished and the remaining surface is now *enumerated*, not unknown. Of
the 239 forms in the API's category tree, **49 are connected**; all **197** others were
probed. 106 of those do hold clean series, but every one is a per-country /
per-region / per-activity / per-company breakdown — formId=436 (IIP by countries) alone
yields 2,064 clean series, 442 yields 1,380, 493 yields 1,343, 355 yields 936. The
headline aggregate behind each was already taken from the corresponding top-level form, so
connecting them would add thousands of granular series without adding an economic concept
the dataset lacks. **Reviewed and decided out of scope** — recorded in `config/sources.yaml`
under `NBK_FORM_COVERAGE` so a later session does not re-run the sweep to rediscover it.
The decision is reversible: re-running the probe reproduces the list if a country or region
cut is ever wanted.

Heuristic worth carrying forward: **forms with FEW clean series (5-8) are the top-level
breakdowns; forms with hundreds are the granular tails.** That single ordering is what
found the external-debt decomposition and the balance-of-payments comparative forms.

## 2026-09-01 — reliability fix and two corrections found while verifying
No new indicators in this entry; it records three things found by checking rather than by
adding.

### 1. imf.org transport flakiness — retry added (transport errors only)
The full four-agency run at 280 indicators came back 279 ok / 1 error: IMF_POPULATION died
on `ConnectionResetError 10054`. Re-running IMF alone then failed on a *different* pair
(IMF_INVESTMENT_RATIO, IMF_GOV_NET_DEBT_RATIO) — a moving target, which is the signature of
flaky transport rather than a problem with any one dataset.

`imf._download` now retries up to 3 times with linear backoff, and **only** on
`ConnectionError`/`Timeout`. HTTP status errors are deliberately NOT retried: a 404 or 500
can mean the dataset moved or changed shape, and the MASTER TASK rules require that to fail
loudly rather than be smoothed over by repetition. Retries print to stderr so a flaky
source stays visible instead of silently passing. Verified: the next IMF run came back
31/31 ok with exactly one retry message in the output — the reset happened and was
recovered, rather than the problem simply not recurring.

### 2. The pipeline's fail-loudly behaviour confirmed working
Worth recording because it is the project's central safety property: on the run with the
IMF error, `update_all.py` correctly refused to publish — `reports/update_report_2026-09-01.md`
shows `Unified dataset updated: False`. The failed indicator did not reach the unified
dataset, and no partial rebuild happened.

### 3. A flaw in how these runs were being verified
Runs had been checked with `python scripts/update_all.py 2>&1 | tail -N`. **That reports
`tail`'s exit code, not the pipeline's** — so a non-zero exit from the pipeline would have
been read as success. It did not cause a wrong conclusion here (the per-indicator run log
and the report were also inspected, and they told the true story), but the habit was
unsound. Verification should read the run log / report, or capture the exit status without
a pipe, as done from here on.

### 4. Category inconsistency corrected
LIFE_EXPECTANCY had been added with `category: demography` while the seven existing
population/health indicators use `category: demographic`. Corrected to `demographic`; the
field is not consumed by the unified builder or metadata, so this is a catalogue-consistency
fix only.

**Still 280/280 indicators, all four agencies verified live.** `pytest tests/ -q` — 29/29.

## 2026-09-01 — thirty-ninth batch: the Taldau browser dependency is GONE (280 -> 287)
The long-standing BNS blocker is solved. Multi-dictionary Taldau indexes — fertility,
mortality, ICT, R&D and the rest — no longer need a live browser session to obtain their
parameters. **Two plain HTTP calls now do it**, which turns BNS from roughly two browser
round-trips per indicator into the same batch workflow used for NBK.

### The method
1. `GET /ru/NewIndex/GetIndex/<INDEX_ID>?keyword=` and scrape the server-rendered JS literal
   for `options.measure.id` — that is `p_measure_id`. It must be `options.measure`, **not**
   `preferredMeasure`, which lists alternative display units and would give a wrong measure.
2. `POST /ru/NewIndex/GetSegmentList` with `node=<ID>&indexId=<ID>&periodId=<P>&keyword=`
   returns the valid dictionary combinations. Element `[0]` is the site's own default (its
   `indexShortController.fOnSectionStoreLoad` does `var selRec = rec[0];`); `p_dicIds` is
   that element's `dicId` split on `+`, and `p_terms` is its `termIds` verbatim.

No cookies, session or CSRF token are involved.

### It was verified before being used, not taken on trust
The method came out of a multi-agent investigation whose independent verification phase
never ran (the agents hit a usage limit), so it arrived as **one agent's unverified claim**.
It was therefore re-tested here from scratch against three parameter sets captured by
browser in *earlier* sessions — independent ground truth the investigation never saw:
LIFE_EXPECTANCY/703906 (measure 154, dicIds 67,64,576), RETAIL_TRADE/702038 (measure 1,
dicIds 67,59,676, 3 segments) and CONSTRUCTION/701885 (dicIds 68,60,71,2987, 6 segments).
All three reproduced exactly, and RETAIL_TRADE's fetched value matched the already-shipped
series (27.7 trillion KZT).

### The trap in this method, and a bug in my own check for it
Segment `[0]` is only the *default* selection — it is **not** guaranteed to be a total. For
indexId 703694 (households with ICT) it resolves to the device type "Телевизор"; for 702755
(enterprises with innovations) to "Подвергавшиеся усовершенствованию + Дополнительные
услуги". Publishing either under the index's general name would be plainly wrong.

The prober therefore flags whether every term is a total — and that check was itself wrong
at first: `termNames` are separated by `' + '`, not by commas, so splitting on commas made
the whole multi-term string count as a total merely because it contained "РЕСПУБЛИКА". Fixed
to split on `+`, after which 702755 and the age-specific fertility index 703842 (15-19 лет)
were correctly reclassified as slices and excluded.

### BNS (7)
- **CRUDE_BIRTH_RATE** (16.43 per 1000, 24 pts from 2001), **CRUDE_DEATH_RATE** (6.61),
  **TOTAL_FERTILITY_RATE** (2.57 children), **INFANT_MORTALITY_RATE** (5.85 per 1000 live
  births), **UNDER5_MORTALITY_RATE** (8.10), **STILLBIRTH_RATE** (5.58).
- **INNOVATION_EXPENDITURE** (1.59 trillion KZT, published only from 2022).

**Independent arithmetic cross-check.** The published rates were checked against series
already in the dataset: `BIRTHS_TOTAL / POPULATION_BNS × 1000` reproduces the published
CRUDE_BIRTH_RATE to two decimals for every year 2021-2025, and the same holds for deaths
and CRUDE_DEATH_RATE. The 2021 death rate of 9.61 against a normal ~6.6 is the COVID spike,
which is the right shape for that year.

**287/287 confirmed indicators connected end-to-end** (76/76 BNS re-verified live).
`pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — fortieth batch: ICT, e-commerce and health capacity (287 -> 297)
First batch built entirely on the new GetSegmentList method — no browser involved at any
point, and the whole batch was discovered, verified and wired in one pass.

**BNS (10):**
- ICT in organisations, with unusually long histories: ORGANIZATIONS_USING_COMPUTERS (20 pts
  from 2005), COMPUTERS_IN_ORGANIZATIONS and COMPUTERS_INTERNET_CONNECTED (21 pts from
  2004 — read together they give a connectivity ratio, 90% in 2024), WORKERS_USING_COMPUTERS
  and WORKERS_USING_INTERNET (19 pts from 2006).
- E-commerce: ECOMMERCE_RETAIL_ORDERS (22.7 million orders) and ECOMMERCE_SERVICES_VALUE
  (451.8 bn KZT), both published only from 2022.
- Health capacity: HOSPITAL_BEDS (104,989), HOSPITAL_BEDS_PER_10K (53.08) and
  DOCTORS_PER_10K (40.57).

Every one was confirmed to be an all-totals slice (`term_names` = "РЕСПУБЛИКА КАЗАХСТАН +
Всего [+ Всего...]") before being connected, per the segment-0 caveat.

**A duplicate avoided by checking rather than assuming.** The doctor-headcount index 704315
turned out to be exactly the already-connected DOCTORS_TOTAL (83,379 in 2024, identical), so
only the density measure was added from that family.

**A cross-check that did NOT come out exact — and why that is fine.** Computing
`DOCTORS_TOTAL / POPULATION_BNS × 10000` gives 40.85 for 2023 against the published 40.57 —
a consistent +0.66% across every year tested. This was investigated rather than waved
through or reported as a match. POPULATION_BNS is the *average annual* population, while the
doctor headcount is measured *at end of year*; dividing an end-of-year numerator by an
end-of-year population (larger than the average by roughly half the ~1.3% annual growth)
reproduces exactly that ~0.65% gap. So the two series are each internally consistent, but
DOCTORS_PER_10K is **not** reproducible from the other two, and is published as the source
gives it rather than recomputed.

**297/297 confirmed indicators connected end-to-end** (86/86 BNS re-verified live).
`pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — forty-first batch: SME sector, housing investment, ICT workforce (297 -> 305)
**BNS (8):**
- The SME block, 20 annual points each from 2005: SME_GDP_SHARE (38.9% of GDP in 2024),
  SMALL_BUSINESS_GDP_SHARE (32.2), MEDIUM_BUSINESS_GDP_SHARE (6.7),
  SMALL_BUSINESS_VALUE_ADDED (43.9 trillion KZT) and MEDIUM_BUSINESS_VALUE_ADDED (9.2
  trillion). This closes a real gap — the dataset had no measure of the private
  small-business economy at all.
- HOUSING_INVESTMENT (3.85 trillion KZT, 13 pts from 2013) — the residential component
  behind the broader INVESTMENT series.
- ICT_SPECIALISTS (43,413 people) and GRADUATES_HIRED (44,644, 25 pts from 2001).

**Two independent cross-checks, both passed:**
1. Internal to the source: SMALL + MEDIUM GDP shares equal the published SME share with
   **0.00 difference** for every year 2021-2024 (32.2 + 6.7 = 38.9).
2. Against a *different* BNS series already in the dataset: SME value added divided by
   GDP_INCOME_METHOD reproduces the published SME share to within 0.12 percentage points
   across 2020-2024, and exactly for 2020 and 2024. That is a real check — it uses the
   income-method GDP series, which has nothing to do with how these SME figures were
   fetched, and it simultaneously confirms the KZT scale of both.

**Deliberately not connected, recorded in sources.yaml under BNS_ENVIRONMENT_AND_CRIME:**
- *Air emissions* — Taldau 705098 stops at 2021 and reports 1.04 million tonnes, while the
  already-connected EMISSIONS series is broader (2.28 million tonnes) and runs to 2025.
  Connecting the candidate would add a series that looks like the existing one but
  contradicts it. Same for the emission-source counts, which also end in 2021.
- *Crime* — all 22 candidates return an **empty** GetSegmentList at periodId=7, so no
  annual national parameters could be resolved. Recorded as unresolved, **not** as "no data
  exists": these are likely published on a different periodicity.
- *Water* — no genuine candidates. Taldau's search matches substrings, and "вода" only hit
  "восстановления" inside unrelated education indicators.
- *Education* — headline schooling metrics (enrolment, student numbers) were not located;
  what surfaced was mostly discontinued or narrow. The two usable ones are connected above.

**305/305 confirmed indicators connected end-to-end** (94/94 BNS re-verified live).
`pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — forty-second batch: government debt structure (305 -> 310)
Applied the NBK enumeration approach to Minfin: downloaded the latest Statistical Bulletin
and listed **all 49 sheets**, diffing them against the sheets this module already mines.
Result: 20 mined, 29 not — and Minfin's remaining surface is now an enumerated list rather
than an open question.

**A sheet with a layout unlike any other used here.** "табл 22 кв" is a WIDE point-in-time
series: one column PAIR per reporting date (млн тенге, then млн долл. США), 22 dates from
2020-01-01 to 2026-07-01 — not the year-to-date-column-per-bulletin-edition shape the other
sheets use. A new parser, `_fetch_debt_structure_row`, handles it.

**Row codes in this sheet are not unique**, which is the real hazard: "1" and "2" appear
under section I (government / National Bank debt) *and again* under sections II and III as
their internal/external split. Matching on the code alone would silently return the wrong
row. Every lookup is therefore anchored to its section ("I.", "II.", "III.") **and**
verified against an expected Russian label before any value is read; a re-ordering upstream
raises `StructuralChangeError` instead of quietly producing wrong numbers.

**Minfin (5):** STATE_DEBT_TOTAL (38.50 trillion KZT), STATE_GUARANTEED_DEBT (2.41
trillion), LOCAL_GOV_DEBT (2.77 trillion), GOV_DEBT_EUROBONDS (4.81 trillion) and
GOV_DEBT_EXTERNAL_USD (17,192 million USD).

**Three cross-checks, all exact:**
- I + II + III = 38,495,061.56 + 2,414,476.28 + 6,000 = **40,915,537.84**, which equals the
  already-connected GOV_DEBT to the cent — confirming these are components of it, not a
  competing measure.
- Section I is *not* simply 1+2+3. The sheet's own footnote says it excludes mutual claims,
  and subtracting row 3.1 (local-government debt owed to the Government, 1,101,375.43)
  reproduces I exactly. The discrepancy was chased down rather than ignored.
- The USD column checks against the sheet's own stated rate: 8,352,366.46 / 485.82 =
  17,192.4 versus the published 17,192.31.

**A duplicate caught before it shipped — and a subtler danger with it.** The first pass also
generated GOV_DEBT_DOMESTIC and GOV_DEBT_EXTERNAL, which the duplicate-ID check rejected:
both already exist, sourced elsewhere, with *identical* values. Worse, the generated
functions were named `fetch_gov_debt_domestic`/`fetch_gov_debt_external` — the same names as
the existing ones, so appending them **shadowed** the originals in the module. The values
happened to match, so nothing would have looked wrong. The whole batch was reverted with
`git restore` and regenerated with those two dropped, rather than patched in place.

**Declined and recorded** (in `sources.yaml`, `MINFIN_BULLETIN_SHEET_COVERAGE`):
- 20 of the 29 unmined sheets are `табл 12.1`–`табл 12.20`, per-region budget execution —
  the granular class already ruled out of scope for NBK.
- `табл 19 кв` (dividends on state shareholdings): the execution figure is stored as the
  **string** `'75945,7**'` with a footnote marker, and its own sub-item (78,612.9) *exceeds*
  the total it belongs to, which the sheet attributes to returned mis-transfers. Publishing
  it would mean picking an interpretation the source itself flags as irregular.
- `табл 23` (primary placement of government securities): per-auction with multi-level
  maturity headers; a monthly placement total would have to be summed across columns by us.
- `табл 5`, `9`, `15`: per-agency departmental granularity.
- `табл 12`, `20 кв`, `21 кв` remain genuinely unexplored candidates.

**310/310 confirmed indicators connected end-to-end** (59/59 Minfin re-verified live).
`pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — forty-third batch: local budgets (310 -> 316)
Closed a real structural gap. The dataset covered Kazakhstan's **republican** budget in
considerable detail but had no measure of the **local** budgets at all — which is where most
education and housing/utilities spending actually happens.

**Minfin (6)**, from Statistical Bulletin sheet "табл 12" (Исполнение местных бюджетов):
LOCAL_BUDGET_REVENUE (17.04 trillion KZT in 2025), LOCAL_BUDGET_EXPENDITURE (16.74),
LOCAL_BUDGET_TAX_REVENUE (8.73), LOCAL_BUDGET_TRANSFERS (7.72),
LOCAL_EDUCATION_EXPENDITURE (6.31) and LOCAL_HOUSING_UTILITIES_EXPENDITURE (2.69).

What these immediately show: transfers from the centre fund **45.3%** of local revenue
against 51.2% from local taxes, and education alone is **37.7%** of all local spending.

**No new parser needed** — `_fetch_bulletin_annual_row` was reused unchanged, and its
existing default behaviour turned out to be exactly right here for two separate reasons that
were *checked live rather than assumed*:
- The sheet's current-period column is headed "2026 ж. қантар-маусым есеп", which the default
  regex skips because 'есеп' is not immediately after the year.
- 2025's merged header sits over the ANNUAL sub-column, so the annual figure (17,039,798.7)
  is picked rather than the January-June one (8,223,337.6) sitting beside it.

**A row-matching trap avoided.** A plain substring match for "Налоговые поступления" also
matches "**Не**налоговые поступления" one row below if case is disregarded, and matching
"Образование" alone would collide with other rows. The matchers therefore support an
exclusion term and use numbered prefixes ("4. Образование"), and the tax row was verified to
return 8,725,097.5 rather than the non-tax 425,962.4.

**Verified identity (2025):** tax 8,725,097.5 + non-tax 425,962.4 + capital sales 172,470.9
+ special 0 + transfers 7,716,267.9 = **17,039,798.7**, exactly the sheet's own "I. ДОХОДЫ".

Only 3 annual points (2023-2025) exist in this sheet — short, and stated as such rather than
padded.

**316/316 confirmed indicators connected end-to-end** (65/65 Minfin re-verified live).
`pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — forty-fourth batch: budget financing flows (316 -> 322)
The last two substantive unmined sheets — "табл 20 кв" (financing by counterparty sector)
and "табл 21 кв" (by financial instrument). With these, the Minfin bulletin enumeration is
worked through.

**Minfin (6), 14 quarterly points each, 2023-Q1 to 2026-Q2:** BUDGET_FINANCING_TOTAL,
_DOMESTIC, _EXTERNAL, _LONG_TERM_BONDS, _BANKS (who actually funds the deficit) and
_INTL_ORGANIZATIONS.

### The reading that would have been wrong
These sheets mix annual columns (2018-2022) with quarterly ones (2023 onward), and the
quarterly magnitudes *look* like the annual ones — which invites reading Q4 as the year
total and the quarters as year-to-date cumulative. **That reading is wrong.** The columns are
PER-QUARTER flows.

This was settled against an independent series rather than by inspection: summing the four
quarters of each year reproduces the already-connected STATE_BUDGET_DEFICIT **to the cent**
— 2023: 2,811,100.59, 2024: 3,586,041.85, 2025: 4,383,871.07, each matching the published
deficit exactly (|sum + deficit| = 0.00). Financing covers the deficit, three years running.
Had the cumulative reading been used, every published value from 2023 on would have been
wrong, and nothing about the numbers themselves would have looked odd.

A second check also passed exactly: domestic + external = total, 0.00 difference in every
quarter.

### Two structural hazards handled
- **Two side-by-side column groups.** Columns 1-19 are the STATE budget; columns 20-38
  repeat the identical period layout for the REPUBLICAN budget. Reading a column index
  without establishing its group would silently mix two different budgets. The boundary is
  located from the header row, never hardcoded, and only the state-budget group is published.
- **A sheet name with a trailing space** — `'табл 21 кв '` — which is what made an earlier
  lookup fail with a KeyError. Sheets are now matched on a stripped prefix.

The 2018-2022 annual columns are deliberately **not** spliced onto the quarterly series:
different frequency, and combining them would misrepresent both.

**322/322 confirmed indicators connected end-to-end** (71/71 Minfin re-verified live).
`pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — exchange rate repaired: 14 points -> 1369
First item from the sector coverage audit. No new indicator: this fixes the one the dataset
already had and could not use. **EXCHANGE_RATE held only 2026-08-19..2026-09-01** — fourteen
days of the most-used macro series in the country — because the fetcher re-pulled a fixed
14-day window every run and discarded everything older.

Now **1369 daily points, 2021-05-10 to 2026-09-01**, range 414.67-549.15. The unified dataset
grew from 10,869 to 12,225 observations on this one repair.

### Three things established live before rewriting
1. **No range interface.** `tdate` alongside `fdate` is silently ignored — the response still
   covers the single `fdate`. `rates_all.xml` is only today's snapshot across 48 currencies.
   One request per date is the only route, so the backfill was ~1,360 requests.
2. **The window is limited and rolling.** 2020, 2015, 2010, 2005 and 2000 all answer
   "информации нет"; 2022-2026 answer normally; the boundary sits in early May 2021. Because
   it rolls forward, history reachable today stops being reachable later — so the fetcher now
   **accumulates**: it reads what is already processed, requests only missing dates plus the
   last two weeks, and merges. Steady-state cost is ~85 requests per run, not 1,360.
3. **The source substitutes a wrong value at the window edge.** This is the part worth
   remembering.

### The trap: a wrong value that looked completely valid
07.05.2021 is a Kazakhstan public holiday. Instead of the "информации нет" it returns for
dates *outside* the window, the endpoint returned **464.77 — the latest rate available at
request time** — while both neighbouring days were 426.99. An 8% one-day round trip that
never happened.

Nothing inside that response looked wrong. It was self-consistent, carrying `change=+37.78`,
which reconstructs 426.99 exactly. It was caught only by comparing the value against its
neighbours after the fact.

Handled two ways: the series starts 2021-05-10, past the edge; and `_assert_no_isolated_spike`
raises on any point that moves >5% from the previous day and >5% back on the next. That check
was **validated against a real event before being trusted** — the Feb-Mar 2022 devaluation ran
428 → 503 over two weeks, a sustained move, and the check stays silent through it, while
firing on nothing across the whole 1367-point backfill. Scanning the backfill also confirmed
the substitution is not systemic: 24 business days inside the window return an honest refusal.

### A self-inflicted break, recorded because it was nearly invisible
The first attempt spliced the new function in by replacing everything from `def
fetch_exchange_rate_usd(` to the next `def` — which also deleted the module-level constants
sitting between them (`MONETARY_AGGREGATES_URL`, `ROW_CODE_M2`, `ROW_CODE_M3`). **122 of 126
NBK indicators then failed** with `name 'MONETARY_AGGREGATES_URL' is not defined`. The
pipeline caught it correctly and refused to rebuild the unified dataset, so nothing wrong was
published. Restored with `git restore` and re-applied by finding the function's true end —
the first following line at column 0 — rather than the next `def`.

**322/322 indicators, 126/126 NBK re-verified live.** `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — rolling windows stopped leaking; annual inflation found (322 -> 324)
Second item from the coverage audit. The exchange rate was not the only series bleeding
history: **three NBK endpoints serve only a recent window and silently drop what falls out
of it.** Established live rather than assumed:

| endpoint | window | parameters |
|---|---|---|
| `get_rates.cfm` | opens early May 2021 | no range interface at all |
| `/api/v1/data/base-rate` | fixed 15 most recent decisions | ignores `limit`, `size`, `count`, `pageSize`, `page`, `fromDate`, `startDate`, `dateFrom`, `all`, `years` — all ten tried, all return exactly 15 rows |
| `/api/v1/data/indicators` | rolling ~6 months | accepts `from`/`to`, ignores `fromDate`/`toDate`; even so, 2010-2015, 2020-2022 and 2024-2025 all return zero rows |

A fetcher that returns only the current window therefore loses data on every run. BASE_RATE
and TONIA now accumulate through a shared `_merge_accumulated` helper, the same fix applied
to EXCHANGE_RATE. Nothing is recovered retroactively — the point is that nothing more is lost.

### Two new indicators, from an endpoint already in use
The indicators widget behind NBK's homepage carries **four** fields, not just the `tonia` one
the project was reading: `baseRate`, `tonia`, `annualInflation`, `inflationTarget`.

**ANNUAL_INFLATION** closes a gap the audit had marked critical: the existing CPI series holds
only month-on-month percent change, so a year-on-year rate could not be read off it at all.
Now 7 points, 12.2% (Feb 2026) declining to 10.2% (Aug 2026), against **INFLATION_TARGET** of
5.0%.

Both are stored **event-dated, not daily**. The source stamps a value on every calendar day,
but annual inflation only steps when a CPI reading is released — across the 186-day window it
took 7 distinct values, changing on 2026-03-03, 04-02, 05-05, 06-02, 07-02 and 08-04. Storing
it daily would bury six real releases under 186 repeated rows. Dates are the day the figure
**appeared**, not the month it refers to: that mapping was not verified, so it is not asserted.

### A judgement call reversed after checking the output
BASE_RATE was first given the same repeat-collapsing as annual inflation, and the series
dropped from 15 points to 6. That is wrong: this endpoint returns one row per **MPC decision**,
and a decision to hold the rate is itself an event. Collapsing silently discarded every hold.
Repeat-collapsing is right for a figure carried between releases and wrong for a record of
decisions — the two look identical in the data and are not. Reverted; 15 decisions retained.

**324/324 indicators, 128/128 NBK re-verified live.** `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — yield curve: investigated across three sources, not connected
Third item from the audit's monetary block, and the first one that does **not** end in a new
series. Recording it as a negative result with the evidence, so the search is not repeated.

- **NBK Open Data** — all three forms of the Securities category checked in full: formId=17
  (primary auctions), 16 (secondary market), 430 (outstanding stock). Every row in 17 and 16
  carries `type='Transactions volume (mln. tenge)'` and nothing else; 430 carries only
  `'mln. of KZT, end of period'`. **There are no yield fields anywhere in NBK's securities
  data** — volumes and stocks only.
- **Minfin bulletin, sheet "табл 23"** — yields *do* exist here. Header column 20 is "ставки
  вознаграждения (интереса), %", with cut-off rates by instrument and maturity (MEOKAM-60,
  MEUKAM-96/156/180, METISKAM-48/84), stored as decimals despite the percent header (0.1502 =
  15.02%, plausible against a 16.75% base rate). Two problems: the sheet is per-auction
  **within one month**, so a series means stitching 13 vintages for ~13 months; and a single
  month can hold two auctions of the same maturity on the same date with different cut-offs —
  23.06.2026 has two MEUKAM-96 results, 14.29% and 15.76%. A date-keyed series cannot hold
  both, and every tie-break is either arbitrary or an aggregate the source does not publish.
- **KASE** — the natural home for yields and for the missing stock index. The site responds
  (`/ru/gsecs/` is ~5 MB) but exposes no JSON surface: `/api/` 404s, `robots.txt` 404s, and the
  page contains **zero** paths matching `api|json|data|ajax|export`. Figures are server-rendered
  HTML, so this route means table scraping — a new agency, a new fetcher, and a parser bound to
  page markup.

**Not connected because publishing it would require inventing a tie-break rule, not because
the data is missing.** The per-auction yields are real and could ship as an event-dated series
(one point per auction, no aggregation) once a rule for same-date same-maturity collisions is
decided — that is a call for the data owner, not one to make silently.

**Still 324 indicators.** `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — the oil block: partly closed, and the gap named precisely (324 -> 329)
Fourth item from the audit, and the one it called the largest: Kazakhstan is an oil exporter
and the dataset contained **nothing about oil** — no price, no production, no oil-linked
revenue. Five indicators now exist; what is still missing is stated exactly rather than left
implied.

### IMF (3) — price and commodity terms of trade
Listing `/structure/dataflow/IMF.RES` turned up two flows sitting beside the WEO one already
in use: **PCPS** (Primary Commodity Price System) and **CTOT** (Commodity Terms of Trade).

- **OIL_PRICE** — 415 monthly points, 1992-01 to 2026-07, 80.19 USD/bbl. This is IMF's APSP,
  the average of Brent, Dubai Fateh and WTI. PCPS has **no standalone Brent series**: its
  indicator codelist was read, and the only crude entries are POILAPSP and POPEC (OPEC
  basket) — every other `*OIL*` code is an edible oil. Labeled as a **world** price, not a
  Kazakhstan export price: KEBCO trades at a differential to Brent this does not capture.
- **COMMODITY_TERMS_OF_TRADE** and **COMMODITY_TERMS_OF_TRADE_FIXED_WEIGHTS** — 413 monthly
  points each from 1992. The source publishes rolling- and fixed-weight variants; rather than
  pick one silently, both are carried. Note this is *commodity* terms of trade, covering the
  commodity basket only — the audit asked for the broader measure, and this is not it.

**A key-discovery trap worth remembering.** This API answers a WRONG series key with **HTTP
200 and an empty body**, not an error — so a mistyped key looks like a working request that
found nothing. Five plausible Brent keys all returned 200 with only a header row. The real key
was read off a full wildcard download, which also revealed that PCPS's COUNTRY dimension holds
the aggregate `G001`, not a country code. The parser's error text now says this outright, so
the next person who hits an empty result is told where to look.

### Minfin (2) — oil-linked budget revenue, named for what it is
Scanning **every** sheet of the bulletin for oil mentions produced a result that shaped the
naming: almost every oil-mentioning row in the budget classification is a **non-oil variant**
— "excluding receipts from oil sector organisations". **The source publishes no single
"oil revenue of the budget" line.**

Two rows are the exception, and are unambiguous: **OIL_EXPORT_DUTY** (crude oil export customs
duty, 901,338 million KZT Jan-Jun 2026) and **OIL_PRODUCTS_EXPORT_DUTY** (10,130 million).
They are named as export duties, **not** presented as total oil revenue, which would overstate
what the source gives.

### Still missing, stated precisely
**Oil production volumes are not in BNS's searchable index.** Probed with "нефти", "нефть",
"сырой", "конденсат", "добыча", "уголь", "уран" — all return zero candidates; "нефт" returns
ten, every one about retail petroleum products or storage tanks. Crude output is simply not
reachable through the Taldau search that works for everything else here, and would need a
different route (energy ministry or an operator). Oil export value and volume are likewise
absent: the existing EXPORTS series is a single total with no commodity breakdown.

**329/329 indicators** (34/34 IMF and 73/73 Minfin re-verified live).
`pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — oil exports: an earlier conclusion of mine was wrong (329 -> 331)
The previous entry recorded that oil export value and volume were "absent" from BNS. **That
was wrong, and it was wrong in the most avoidable way**: the data sat in the very workbook
this project already downloads for EXPORTS. Only the national TOTAL row was ever being read.
The same sheet carries a full HS-code breakdown, and each month spans three columns —
tonnes, additional unit, thousand USD — so both the volume and the value of crude exports
were there the whole time.

The lesson is not "search harder". It is that **an already-connected source was never fully
read**, and a negative conclusion was drawn about a file that had not been looked past row 4.

**BNS (2):** OIL_EXPORTS_VOLUME and OIL_EXPORTS_VALUE, HS 270900, 89 monthly points,
2019-01 to 2026-06.

### Summing regions — and earning the right to do it
There is **no national product block**: crude oil appears only inside the 10 regional blocks
that export it, so a national figure requires summing regions. That is normally exactly the
self-made aggregate this project refuses to publish. It was allowed here only after proving
the partition is complete and non-overlapping:

- every code in column A is **6 digits** — 12,230 rows checked, so the breakdown is flat and
  there are no chapter subtotals to double-count;
- summing **all** product rows across **all** regional blocks reproduces the published
  national total **to the last decimal**: 14,202,968.530 tonnes and 6,471,046.013 thousand
  USD for January 2026, a difference of 0.000000%.

That proof is **re-run on every fetch**, not just once. It holds for **178 of 180** month/unit
checks across 2019-2026.

### The guard fired on its first real run, and that changed the design
The two failures are both in 2022 — worst **+1.513%** in September — around the mid-2022
creation of the Abai, Jetisu and Ulytau regions. My first version raised on any mismatch and
so refused the entire indicator over two bad months out of 180. That is disproportionate:
those months are now **skipped and reported on stderr**, while a broad failure (>10% of
checks) still raises, because that would mean the structure changed rather than one month
being odd.

Worth noting plainly: verifying the partition on a single sheet was **not** sufficient
evidence for all sheets. The guard caught what my spot-check had missed.

### Validated against two independent facts
- **Annual volumes**: 70.0, 70.6, 65.7, 60.6, 70.7, 71.0, 76.3 million tonnes for 2019-2025 —
  matching Kazakhstan's known crude export level of roughly 65-75 Mt a year.
- **Implied price**: dividing value by volume tracks the world OIL_PRICE within about
  5 USD/bbl every year (2022: 97.1 vs 96.4; 2023: 81.7 vs 80.6; 2024: 82.4 vs 79.2). Monthly
  implied prices wobble far more, which is the shipment-versus-payment lag, not a parsing
  error — stated rather than smoothed over.

**331/331 indicators** (96/96 BNS re-verified live). `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — oil production found; the second wrong conclusion corrected (331 -> 332)
Pointed at the right publication by the user. **OIL_PRODUCTION** now exists: crude oil
including gas condensate, thousand tonnes, monthly.

This is the second negative conclusion in two entries that turned out to be wrong, and the
reason matters. Oil production genuinely **is** absent from the places that were checked —
Taldau's full 3,700-indicator catalogue, and the stat.gov.kz industrial cubes, which are
index-only and stop at 2023. What was not checked was the **publication** layer:
"Основные показатели работы промышленности Республики Казахстан", sheet 3 ("Произведено
продукции в натуральном выражении"), row "Нефть, включая конденсат газовый, тыс.тонн".

Enumerating a source's *databases* is not the same as enumerating what it *publishes*. Both
oil misses came from stopping at the first layer.

### Implementation notes
- Each edition reports **one month**, in columns [previous month, reporting month, YTD, same
  month last year, same period last year], so one download yields three monthly points. The
  YTD columns are a different frequency and are deliberately not mixed in.
- The site keeps a **short archive** — three monthly editions on 2026-09-01 — so the series
  is **accumulated across runs** and grows month by month, as EXCHANGE_RATE does. It starts
  with 7 points and has gaps, which is stated rather than filled.
- **Element ids are resolved from the page on every run, never hardcoded**: editions are
  republished under new ids, and the HTML card-to-id mapping proved unreliable when parsed
  directly. Only workbooks that actually contain the expected sheet and row are used, and the
  reporting month comes from each file's own cover date rather than from the page text.

### Validated three ways
- Year-to-date for 2026 reads 53,208 thousand tonnes over seven months (~91 Mt/year) against
  58,358 for the same period of 2025 (~100 Mt/year) — an 8.8% year-on-year fall, consistent
  with Kazakhstan cutting back from its 2025 record.
- ~100 Mt of 2025 output against **OIL_EXPORTS_VOLUME**'s 76.3 Mt for the same year is a 76%
  export ratio, the rest refined domestically — the right shape for Kazakhstan, and a check
  that uses an indicator added only an entry earlier.
- An initial reading of "~91 Mt/year" as the general level was **wrong** and was corrected:
  it is the 2026 pace, not the 2025 one. Recorded because the first draft of the source note
  asserted it.

**332/332 indicators** (97/97 BNS re-verified live). `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — monthly industry, and the staleness finding answered (332 -> 336)
Sheet 2 of the same publication that supplied OIL_PRODUCTION. This is what answers the
audit's **staleness** finding rather than its coverage findings: IND_PROD and its three
sub-indices are annual and stop at **2023**, because they come from the stat.gov.kz cubes,
which are no longer updated. The publication layer carries the same concepts monthly and
current.

**BNS (4):** INDUSTRIAL_OUTPUT (5.48 trillion KZT in July 2026),
INDUSTRIAL_PRODUCTION_INDEX (year-on-year, 100.1), MINING_OUTPUT and MANUFACTURING_OUTPUT.
The two sector series give the resource-versus-processing split the dataset lacked.

The old annual series are left in place rather than deleted: they hold 2009-2023 history the
monthly ones cannot reach, and the note on each new indicator says which is which.

### The unit is written three different ways
The guard on the value unit **fired twice during development**, and each time it was a real
variant, not a false alarm: editions write it as `млн. теңге`, `млн.теңге` (no space) and
`млн. тенге` (Russian **е** for Kazakh **ң**). Same unit every time. The check now strips
whitespace and accepts either spelling — the same class of source inconsistency as the
Latin/Cyrillic **Н** found earlier in Minfin's property-tax rows.

Worth stating plainly: the guard was written to catch a rescaling, and what it actually
caught was spelling drift. It still earned its place — without it, a genuine unit change
would pass silently, and the two variants would have been discovered only by someone
noticing odd numbers later.

### Internal check
At July 2026: mining 2,539,304 + manufacturing 2,605,482 = 5,144,786 against total industry
5,479,507. The 334,721 difference is electricity and water supply, which the same sheet
reports separately (water alone is 54,991) — so the sector rows account for the total.

**336/336 indicators** (101/101 BNS re-verified live). `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — fixed capital investment, and a trap that cost a wrong series (336 -> 338)
Third staleness fix from the publication layer: the annual INVESTMENT series stops at **2022**.
INVESTMENT_FIXED_CAPITAL and INVESTMENT_INDEX now carry current, monthly-published figures —
11.46 trillion KZT for January-July 2026, growing 8% year on year in real terms.

The figures are **year-to-date cumulative, not monthly flows**. The sheet compares against
"соответствующему периоду прошлого года", and 11.46 trillion over seven months is about 19.6
trillion a year, which is Kazakhstan's actual investment scale — a single month could not be.
Labelled as cumulative rather than quietly mixed in with monthly series.

### The section mixes monthly and annual editions
This is the trap, and it produced a visibly wrong series before it was caught. The
investment section publishes **monthly** editions alongside an **annual** one. Read naively —
"published in month M, therefore reports month M−1" — the annual file (published 03.07.2026)
became *June 2026* at **23.5 trillion**, against July's 11.46.

A cumulative series cannot fall. That impossibility is what exposed it; nothing about 23.5
trillion looks wrong in isolation, and it sits in exactly the range a plausible figure would.

Two fixes, because one was not enough:
- Editions are now told apart by the **gap to their next publication**, which each file states
  on its own cover — about a month for monthly, a year for annual. That removes the bad row.
- A **monotonicity check** raises if a year-to-date value ever falls inside a calendar year.
  That is the property that caught this, so it is now enforced rather than relied on being
  noticed. The periodicity filter is the fix; the monotonicity check is the net beneath it.

After the fix the series reads 3.46, 4.94, 6.74, 9.51, 11.46 trillion for March-July 2026.

**338/338 indicators** (103/103 BNS re-verified live). `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — export and import price indices (338 -> 340)
Closes a high-priority external-sector gap. The dataset held physical **volume** indices for
trade but no **price** indices, so nominal trade movements could not be split into price and
quantity, and terms of trade could not be built from actual trade at all —
COMMODITY_TERMS_OF_TRADE from the IMF covers only the commodity basket.

June 2026: export prices **127.8**, import prices **101.6** year on year — a sharp
terms-of-trade gain, and in the same direction as the oil price over that window.

### Two ways this file could have been read wrong
- **Its cover carries no publication date**, unlike every other publication used here. The
  reporting month is taken from the sheet's own header text instead ("Июнь 2026г. к"), which
  is the better source anyway: it states the period the numbers describe rather than when the
  file was posted.
- **The total row carries seven comparisons side by side** — against the previous month,
  against last December, against the same month a year earlier, against December 2020, and
  three quarterly ones. Only the third is a normal year-on-year monthly index. Picking the
  wrong column would have produced a series that passes any plausibility check while meaning
  something else entirely: the December-2020 base column reads **234.4** for exports, which
  looks like a perfectly reasonable index number.

One edition sits on the page at a time, so the series accumulates across runs and starts with
a single point — stated rather than padded.

**340/340 indicators** (105/105 BNS re-verified live). `pytest tests/ -q` — 29/29 passing.

## 2026-09-01 — annual inflation: it was inside a file already being downloaded (340 -> 342)
Closes the audit's **critical** inflation gap. The audit's own wording was that CPI carries
only month-on-month change, "from which a year-on-year rate cannot be read directly" — and
that was true of the *series*, but not of the *file*. Element 1549 has a comparison-type
dimension with **thirty** values, and the project was filtering on one of them.

**This is the same mistake as the oil exports, in a different file**: an already-connected
source read only along the axis first needed. Twice in one session, a "missing" indicator was
sitting inside a download the pipeline already performs.

**BNS (2):** CPI_YOY (178 monthly points, 2011-01 to 2025-10) and CPI_YTD (cumulative since
December, the form Kazakhstan's own commentary quotes).

The comparison dimension also holds fixed bases at December 2000, 2001, 2002, 2005, 2010,
2015, 2018, 2020 and 2022. The **product** dimension, though, holds only "Товары и услуги" —
so the audit's food / non-food / services split is genuinely not in this file and stays open.

### Verified two independent ways
- **Against our own CPI**: compounding twelve month-on-month changes reproduces the published
  year-on-year index to within **0.11 index points** (rounding) for every month tested —
  111.79 vs 111.8, 112.23 vs 112.2, 112.57 vs 112.6.
- **Against a different source**: 12.6% here for October 2025 runs into 12.2% in February 2026
  and 10.2% by August 2026 in the NBK-sourced ANNUAL_INFLATION added earlier today. Two
  agencies, one trajectory.

**342/342 indicators** (107/107 BNS re-verified live). `pytest tests/ -q` — 29/29 passing.
