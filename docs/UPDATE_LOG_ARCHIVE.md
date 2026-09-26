# Update Log — archive (2026-08-30 .. 2026-09-15)

Older entries of project_knowledge/UPDATE_LOG.md, moved here on 2026-09-26 so the Claude Project's
context holds only the recent log. Oldest first; nothing edited.

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

## 2026-09-01 — monthly retail and wholesale trade (346 indicators, 14,084 observations)

- Closed the audit's monthly-retail gap in the real sector. `RETAIL_TRADE_MONTHLY`,
  `WHOLESALE_TRADE_MONTHLY`, `RETAIL_TRADE_INDEX_MONTHLY`, `WHOLESALE_TRADE_INDEX_MONTHLY`
  from the BNS publication "Статистика внутренней торговли".
- Same staleness pattern as industry and investment: `RETAIL_TRADE`, `WHOLESALE_TRADE` and
  `RETAIL_TRADE_VOLUME_INDEX` already existed but are all ANNUAL, from the stat.gov.kz cubes.
  The publication layer carries the same concepts monthly and current.
- **Finding the section took three wrong guesses.** `stat-dom-trade`, `stat-trade` and
  `stat-domestic-trade` all return HTTP 500. The real slug is `local-market`, and it sits under
  `/economy/` rather than `/business-statistics/`. Guessing URL paths kept failing; enumerating
  the site's own industry index (26 sections) found it immediately. Recorded because this is the
  third time this session that guessing a BNS path cost more than reading a listing.
- Two repeated-label traps, both caught before they produced wrong numbers:
  - Sheet 1 repeats every row label — "Розничная торговля, всего" appears once nationally and
    again under a "Сельская местность" heading for rural areas alone (718.9bn against 9,016bn
    KZT). Matching is first-hit.
  - Sheet 2 carries "Республика Казахстан" twice, under separate "Розничная торговля" and
    "Оптовая торговля" headings. Lookups are anchored to the section heading — the same fix the
    Minfin debt-structure rows needed.
- Added a genuine cross-check: sheets 1 and 2 independently publish the reporting month's value,
  so the index fetchers compare them and refuse the edition on a mismatch. All four editions
  online agreed exactly.
- Scale cross-check against the existing annual series: May 2026 retail of 1.93 trillion KZT
  annualises to ~23 trillion against annual `RETAIL_TRADE` of 23.56 trillion for 2024.
- Reporting month read from the sheet's own header ("май 2026г."), not the publication date.
- Four editions online (April–July 2026), so these series ACCUMULATE across runs.
- Verified live: 111/111 BNS fetchers OK, `pytest tests/ -q` 29/29 passing.

### Real-sector audit items still open
Quarterly real GDP — the national-accounts section holds labour-productivity publications, and
the quarterly GDP cube (element 4439) has only a regional dimension, no physical-volume index.
CPI breakdown by group (food / non-food / services) — confirmed absent from element 1549, whose
product dimension holds only the "Товары и услуги" total. Both need a different dataset.

## 2026-09-01 — monthly construction (348 indicators)

- `CONSTRUCTION_OUTPUT` and `CONSTRUCTION_INDEX` from the BNS publication "Основные показатели
  предприятий и организаций, осуществляющих строительную деятельность". Closes the audit's
  construction gap in the real sector.
- **The mixed-periodicity trap again, and this section is worse than investment**: it publishes
  monthly (+30d), quarterly (+91d) and annual (+367d) editions under the SAME sheet name and the
  SAME row label. The annual edition reads 10.85 trillion KZT for 2025 and would have been stored
  as a monthly year-to-date point — the same failure that produced the bogus 23.5-trillion "June"
  investment figure before the edition-gap filter existed.
- This cover, unlike the investment one, states both facts outright: the date of the next release
  (so the cadence is known rather than guessed) and the period covered ("Январь-июль 2026 года").
  The reporting month is now READ from the cover instead of inferred from the publication date,
  and editions are admitted only when the release interval is monthly. The annual edition fails
  both tests independently — its period text carries no month name.
- Values are year-to-date cumulative and guarded for monotonicity within each calendar year.
  April–July 2026: 1.74, 2.41, 4.07, 5.06 trillion KZT — strictly increasing.
- 5.06 trillion for seven months against 10.85 trillion for all of 2025 is not a contradiction of
  the +15.3% the same row reports: Kazakhstan's construction is strongly back-loaded.
- Verified live: 113/113 BNS fetchers OK, 29/29 tests passing.

### Agriculture: monthly output not found in this section
The agriculture section (`stat-forrest-village-hunt-fish`) holds grain balances, livestock,
sown-area and greenhouse publications, plus long-run ANNUAL regional series in a different
"Показатель" format (2000 onward, by KATO region). Monthly gross agricultural output is not
among them. Not connected rather than guessed at.

## 2026-09-01 — quarterly labour market and wages (356 indicators, 14,106 observations)

- Eight indicators from two BNS publications: "Основные индикаторы рынка труда" and
  "Численность наемных работников, фонд заработной платы, среднемесячная заработная плата".
  `LABOR_FORCE`, `LABOR_FORCE_PARTICIPATION_RATE`, `EMPLOYED_QUARTERLY`, `UNEMPLOYED_PERSONS`,
  `YOUTH_UNEMPLOYMENT_RATE`, `LONG_TERM_UNEMPLOYMENT_RATE`, `AVG_WAGE_QUARTERLY`,
  `REAL_WAGE_INDEX_QUARTERLY`.
- Closes the audit's participation-rate gap, which was missing entirely. Without it a falling
  unemployment rate cannot be told apart from people leaving the labour force.
- Both sections mix annual and quarterly editions under identical titles and sheet names — the
  construction trap again. The discriminator here is cleaner than a release-interval heuristic:
  quarterly editions name their quarter on the cover ("I квартал 2026 года"), annual ones say
  "2025 год". Both the cover quarter and the release interval must agree.
- **Added an identity check that is not a restatement**: the labour table states labour force,
  employed and unemployed independently, so employed + unemployed must equal the labour force.
  It runs on the already-open worksheet at no extra download. Verified it FIRES on a wrong value
  rather than only passing on a right one — a guard that never fires is worthless. Both editions
  agree exactly: 9,392,025 + 446,049 = 9,838,074 for Q1 2026.
- Wage cross-check across independent sources: annual `AVG_WAGE` reads 443,315 KZT for 2025 and
  the quarterly publication reads 445,068 KZT for Q1 2026.
- Youth unemployment (3.0%) sits BELOW the headline rate (4.5%) — the reverse of the usual
  pattern, recorded so it is not read as a labour-market strength without checking.
- Real wages flat (99.8) while nominal wages rose 11.5% year on year.
- Verified live: 121/121 BNS fetchers OK, 29/29 tests passing.

### Process note — the escaping trap, hit again
Splicing code through a shell heredoc lost one backslash level and wrote a literal newline inside
a string literal, breaking the module. Two lessons, both now applied: build the replacement text
in a scratchpad FILE rather than inside a heredoc, and validate before writing rather than after —
the previous attempt wrote the broken file first and only then discovered it would not parse.

## 2026-09-01 — monthly transport (360 indicators, 14,118 observations)

- `FREIGHT_TURNOVER_MONTHLY`, `PASSENGER_TURNOVER_MONTHLY`, `FREIGHT_CARRIED`,
  `PASSENGERS_CARRIED` from "Основные показатели работы транспорта по видам экономической
  деятельности". Closes the audit's turnover gap: `FREIGHT_TURNOVER` was annual and
  `PASSENGER_TURNOVER` was annual and stopped at 2016.
- **The cells in this sheet are TEXT, not numbers.** openpyxl returns `'540451.13'` as a string.
  The `isinstance(cell, (int, float))` filter that every other fetcher in the module uses would
  have found an empty list here and returned nothing — a silent miss, not an error. Values are
  parsed from text, and columns are addressed by absolute position rather than by position among
  the numeric cells, which is meaningless when some cells hold a dash.
- The cover carries no publication date, only the period ("Январь-июль 2026 года") — which is the
  better of the two anyway, and is what the reporting month is taken from.
- **One reconciliation passed and one failed, and the failure is recorded rather than papered
  over.** Freight turnover: 298,327.53 mln t-km for January–July 2026 annualises to 511 bn
  against 512.6 bn in the annual series for 2025 — effectively exact. Passenger turnover:
  54,627.9 mln p-km annualises to about 94 bn against 266.8 bn in the annual series for 2016,
  roughly a third of the old level.
- Since freight from the *same row* reconciles, the passenger discrepancy is not a units or
  scaling error in the sheet. The cause is not established: the long-run archive in that section
  covers passengers *carried*, a different indicator, so nothing published there resolves it.
  The two passenger series are kept separate and marked "do not splice". Left as an open question
  instead of an invented explanation.
- Year-to-date values guarded for monotonicity; three editions online (May–July 2026), strictly
  increasing on all four series.
- Verified live: 125/125 BNS fetchers OK, 29/29 tests passing.

## 2026-09-01 — monetary and fiscal audit items investigated, three declined with evidence

No new indicators in this entry. Three audit gaps were chased to a firm answer and recorded so
they are not re-investigated from scratch.

**Bank total assets and capital — declined.** Three NBK forms could have carried them; all three
were probed live and all three are unusable:
- `formId=1` "Total balance sheet of tier two banks" — 1,918 rows, 44 monthly dates, 41 clean
  series. It lists 45 individual balance-sheet account groups and publishes **no total** for
  assets, liabilities or equity. Summing the asset lines would publish an aggregate the source
  does not itself publish.
- `formId=60` "Сведения о собственном капитале, обязательствах и активах" — the title promises
  exactly this, but it is per-bank (23 banks) and **ambiguous**: seven rows per bank-date with
  every field identical and only the amount differing. The API strips the line-item labels, so
  which row is assets and which is capital cannot be known. Same failure mode as `formId=484`.
- `formId=50` "Монетарный обзор Национального Банка" (the NBK balance sheet, also an audit item)
  — 24 clean monthly series, but its only classification field is `row_code` (`1`, `1.1.1`, `2`,
  `3.3`) with no labels anywhere in the response.

**Correction to an earlier conclusion.** The `NBK_FORM_COVERAGE` note recorded that the 197
unconnected forms are "granular breakdowns". That description was too coarse for `formId=1`: a
balance sheet's top lines would be headline indicators, not a breakdown. They are simply absent
from the form. The scope note now says so specifically rather than resting on the blanket claim.

**National Fund inflows — not available.** The bulletin's National Fund sheet
(`табл 17 кв+1мес`) was dumped: it carries only the portfolio composition (stabilisation and
savings portfolios, bonds, equities, gold, alternative instruments, targeted requirements, total),
all already connected. No inflow row exists there. Left open rather than substituted with a
different concept.

All three become connectable immediately if NBK publishes the `formId=50` row-code legend or adds
a line-item field to `formId=60`.

## 2026-09-01 — income inequality and poverty depth (364 indicators, 14,124 observations)

- `GINI_COEFFICIENT`, `DECILE_INCOME_RATIO`, `POVERTY_DEPTH`, `POVERTY_SEVERITY` from sheet 5 of
  the quarterly BNS publication "Основные показатели дифференциации доходов населения".
  Closes the audit's Gini gap: the dataset held `POVERTY_HEADCOUNT` but nothing about how income
  is *distributed*, so a falling poverty rate could not be told apart from a widening gap above
  the poverty line. Gini 0.283 for Q1 2026, decile ratio 5.66.
- **The country row is labelled in Kazakh** — "Қазақстан Республикасы" — even in the
  Russian-language file, where every other publication in this project uses "Республика
  Казахстан" or "Всего". Matching on the Russian form finds nothing.
- The sheet publishes two Gini coefficients, over decile and quintile groups (0.283 and 0.269).
  The decile one is the headline; the quintile variant is a methodological alternative of the
  same concept and was deliberately not added as a second series.
- Reused `_quarterly_editions` unchanged — the annual-versus-quarterly cover filter built for the
  labour market applied here without modification.

### My own mistake, caught and fixed before commit
I registered these four under a new `category: social`, inventing a thirteenth category for four
indicators. That is the same error as the earlier `demography`/`demographic` slip. Corrected to
follow the existing convention: the two poverty measures go to `demographic` alongside
`POVERTY_HEADCOUNT`, the two distribution measures to `labor` alongside `PER_CAPITA_INCOME` and
`REAL_INCOME_INDEX`. Eleven categories, as before.

### Housing price index — not connected, two independent reasons
It exists on Taldau (index 703083, "Индексы цен на рынке жилья") but is unusable as a current
indicator, both verified live:
1. **Frozen.** Segment metadata reports maxDate 2020-12-30, and a live fetch returned 35 quarterly
   points from 2012-03-31 to 2020-12-31 and nothing after — six years stale.
2. **The default segment is the wrong concept.** Taldau's `segment[0]` is "Арендная плата за
   неблагоустроенное жилье" — rent for unimproved housing, a sub-category, not the headline
   sale-price index. Same trap already recorded in `TALDAU_PARAM_DISCOVERY` (the ICT index
   defaults to "Телевизор"). No endpoint for enumerating a dictionary's terms could be found
   (`GetTermList`, `GetDicTerms`, `GetTermTreeData` all 404), so the right housing category could
   not be selected without a browser session.

Not in the publication layer either — the route that rescued `OIL_PRODUCTION` and the industry
series after Taldau failed for them. The prices section publishes transport tariffs,
socially-significant food prices, export/import price indices and retail food prices; the
construction section publishes no price tables at all.

## 2026-09-01 — balance of payments sub-balances (368 indicators, 14,225 observations)

- `BOP_GOODS_BALANCE`, `BOP_SERVICES_BALANCE`, `BOP_PRIMARY_INCOME`, `BOP_SECONDARY_INCOME` from
  NBK `formId=324` — the form already supplying `CURRENT_ACCOUNT_BALANCE`. 24 quarters,
  2020-04-01 to 2026-04-01.
- Closes the audit's BoP gap. The dataset held the current account as one number, so the deficit
  could not be decomposed — and for Kazakhstan the decomposition *is* the story: in Q2 2026 goods
  ran a **surplus** of 4,068.9 mln USD while primary income ran a **deficit** of 5,956.5 mln.
  The current account deficit is an income deficit, not a trade deficit — profit repatriation by
  foreign investors in oil. That means it can worsen in a strong oil year, which the headline
  number alone completely hides.

### Rejected formId=481 despite four times the history
`481` ("standard presentation") carries the same five lines back to 2000-04-01 and its headline
matches the stored series to six decimals. It was fully built out, tested, and then rejected: on
**ten quarters in 2023–2024 it returns two different amounts under an identical classification
signature** — 2023-04-01 goods as both 5,169.046879 and 5,232.056879, a 1.2% gap, with nothing in
the row to tell them apart. They look like two vintages of a revised figure with no vintage field.
Taking the larger, the smaller, or the last-returned would each be a guess. Forms 479 and 483 have
the same defect on two quarters each. `324` has none.

### Three things this cost, recorded because they are easy to repeat
1. **Reading the field list off row zero understates the form.** My first probe reported four
   classification fields. The form actually has fourteen — `instrument_type_code`,
   `instrument_subtype1..4_code`, `investor_type_code`, `sector_economy_type_code` and others
   appear only on subsets of rows. Pinning four fields matched 208 rows I thought were one series.
2. **My first identity check was unsound and passed anyway.** It built a dict keyed by date and
   silently overwrote duplicate rows, so it compared whichever row came last and reported "holds
   exactly on all 105 quarters". Once duplicates were handled properly the same data raised. A
   check that cannot fail is worse than no check, because it is quoted as evidence.
3. **`481` serves exact duplicates at scale** — 28,704 rows returned, matching its own
   `totalRows`, of which only 14,975 are distinct, some repeated four times inside a single page.
   Harmless in itself, but it is what made the unsound check look like it passed.

### Two traps that the full-signature pinning caught
- On `324` the code `Goods` appears **twice**: the goods balance, and a sub-item under
  Travel → Personal for goods bought by travellers, 0.0 throughout. Only the instrument fields
  distinguish them.
- `324` writes the unit as `mln USD` while `481` writes `USD mln` — the same field, words in the
  opposite order, in two forms of the same publication. `324` also pads `instrument_type_code` as
  `" Goods and services"` and capitalises `period`. Stripping and case-folding absorb the padding
  and the casing but not the word order; that had to be read off a live row.

The accounting identity is now re-checked on every fetch — goods + services + primary + secondary
must equal the current account — and it was verified to **fire** when a component is perturbed by
50 mln, not merely to pass on real data. In the unified dataset the four components sum to exactly
the stored `CURRENT_ACCOUNT_BALANCE` (−2008.012157 for 2026-04-01).

Verified live: 132/132 NBK fetchers OK, 29/29 tests passing.

## 2026-09-01 — state budget execution within the year (374 indicators)

- Six year-to-date series from sheet "табл 3" of the Minfin Statistical Bulletin:
  `STATE_BUDGET_REVENUE_YTD`, `STATE_BUDGET_EXPENDITURE_YTD`, `STATE_BUDGET_DEFICIT_YTD`,
  `STATE_NON_OIL_DEFICIT_YTD`, `STATE_NET_BUDGET_LENDING_YTD`,
  `STATE_FINANCIAL_ASSETS_BALANCE_YTD`. Closes the audit's monthly-budget-execution item.
- The dataset already read this exact sheet — but only its **annual** column, giving three points
  each ending at 2025. The fiscal position could not be tracked within a year at all. Column 5 is
  the current year-to-date figure, and across the thirteen bulletin vintages it gives 11 in-year
  points from 2025-03-31 to 2026-06-30. The source was already connected; a column was being left
  unread. That is the third time this session the gap turned out to be inside a source already in
  use, after oil exports and the CPI comparison dimension.
- Two of the six were not in the dataset at any frequency: net budget lending and the balance on
  financial-asset operations — the two lines that sit between the revenue-expenditure gap and the
  headline deficit.
- **The budget identity is checked, not assumed**: revenue − expenditure − net lending − financial
  assets balance = deficit. All five are published independently on the sheet. For January–June
  2026: 15,036,307.107 − 16,677,640.518 − 255,161.716 − 379,454.476 = −2,275,949.603, exactly the
  stated line V. Verified across **all 11 dates** by cross-checking the six series against each
  other — zero discrepancies — and the guard was verified to **fire** when the deficit lookup is
  pointed at the non-oil deficit row instead.
- Two layout traps: `_fetch_bulletin_row`'s default `value_col=-2` lands on the *Russian label*
  here, since this sheet puts its labels in the last columns; and rows must be matched on the full
  section text, because "III. ЧИСТОЕ БЮДЖЕТНОЕ КРЕДИТОВАНИЕ" and "VI. НЕНЕФТЯНОЙ ДЕФИЦИТ" collide
  with looser matching.
- `_fetch_bulletin_row` gained an optional `note_override`: its built-in note says "republican
  budget only", true of every sheet it served until "табл 3", which is the **state** budget
  (republican plus local). Shipping the default note would have misstated what the numbers cover.
  Existing callers are untouched.
- The series reset each January (26.8 trillion KZT by 2025-11-30, then 1.83 trillion at
  2026-01-31) — the expected cumulative pattern, not a collapse.

### External debt service — not connected
Two NBK forms carry the phrase; both were probed live and neither is usable, for the same two
reasons. `formId=346` and `formId=393` are **forecasts** — their `repayment_type` values are
literally "Principal (forecast)" and "Interests  (forecast)" — and neither publishes a **total**:
both break the forecast across 11–13 forward repayment windows and 4–5 sectors with no "Total"
member in either dimension. Summing the windows would be an aggregate the source does not publish.
The interest component of actual service sits inside `BOP_PRIMARY_INCOME`, which is connected.

## 2026-09-01 — completing the KASE form; dollarization and the stock index declined (378 indicators)

- `EXCHANGE_RATE_CNY_KASE`, `KASE_CNY_VOLUME`, `KASE_EUR_VOLUME`, `KASE_RUB_VOLUME` from
  `formId=35` "Results of trades on KASE" — a 2×4 grid of which exactly one cell was being read.
- **The Chinese yuan was absent from this dataset entirely** — no KASE rate, no OTC rate, no
  volume, at any frequency — although China is one of Kazakhstan's largest trade partners and this
  form was already being downloaded every run for `KASE_USD_VOLUME`. Fourth time this session the
  gap sat inside an already-connected source, after oil exports, the CPI comparison dimension and
  the state budget's year-to-date column.
- Cross-check against an independent series: dividing the NBK official `EXCHANGE_RATE` by the KASE
  yuan rate gives an implied USD/CNY of **7.24 at end-January 2025**, matching the market rate
  then, drifting smoothly to **6.62 by end-August 2026**. Two series from different collection
  processes agreeing on a third quantity neither of them mentions.
- Scope decision: the KASE rates for USD, EUR and RUB were deliberately left out. `EXCHANGE_RATE`
  (official) and `EXCHANGE_RATE_*_OTC` (over-the-counter) already cover those currencies, and a
  third near-identical rate per currency invites silent substitution in analysis. The yuan is
  different because nothing covered it at all.

### Dollarization — not connected
`formId=42` "Information on the structure of deposits" is the obvious source and does carry the
needed `currency` dimension (National / Foreign, 44 monthly dates). It is still unusable: it
returns **ten rows per (date, currency) with ten different amounts and no field distinguishing
them** — verified live on 2026-08-01, National currency, amounts from 1.35 to 19,444.60 bln tenge
with every classification field identical. Taking the largest as the total would be an
interpretation the source does not state. This is the **third** NBK form found with that exact
defect, after `formId=60` (bank capital and assets) and `formId=484`.

Household deposits split by currency *are* held with proper labels (from `formId=261`), so a user
can compute a household dollarization ratio from published components. It is not published here
because building it means summing three series into an aggregate the source does not publish.

### KASE stock index — still not connected
`formId=35` is the only KASE form in the NBK API and carries FX trading only. Confirms the earlier
finding: kase.kz responds but exposes no JSON surface, so the index needs HTML scraping — a new
agency and a parser tied to page markup. Four guessed API paths all returned 404, consistent with
that.

## 2026-09-02 — NBK form re-sweep, and transaction counts (384 indicators, 14,771 observations)

I recorded earlier that the blanket verdict "the 197 unconnected NBK forms are granular
breakdowns" was too coarse, after `formId=1` turned out to be a balance sheet whose top lines
would be headline indicators. This is the follow-through on that admission rather than leaving it
as a footnote.

### The re-sweep
All 176 currently-unconnected forms, one page each, classified by **what their classification
fields actually are** rather than by how many series they yield:

| | |
|---|---|
| 84 | geographic, per-entity or per-industry breakdowns |
| 60 | multi-dimensional breakdowns |
| 16 | no classification field at all — but 3 to 86 **unlabelled rows per date** |
| 4 | only an unlabelled `row_code` |
| 11 | few enough series to be headline candidates |
| 1 | empty |

The 16 "no classification" forms are not single-series forms, as their shape suggests — they are
label-stripped, the same defect already recorded for `formId=60`, `formId=42` and `formId=484`.
That defect is now known to affect **at least twenty forms**, which is a more useful thing to know
than the count of breakdowns.

Of the 11 candidates, checked one by one: `formId=417` has no unambiguous series at all;
`formId=61` has exactly one and nothing else; `formId=181` is clean only on its Euro leg;
`formId=396` duplicates external debt already held. Two were worth connecting.

### formId=33 — the strongest-looking find, declined
"Official Foreign Exchange Rates on average for the period": official averages for USD, EUR, RUB,
CNY and GBP, properly labelled. Declined for two reasons, both established live.

**Its `report_date` is shifted one month forward of the period it describes.** The form reports
472.1259 at 2026-08-01, which is the average of the daily official `EXCHANGE_RATE` over **July**
(472.12); and 487.8527 at 2026-07-01, which is the **June** average (487.85). Nothing in the API
says so. Connecting it naively mislabels every point by a month. Recorded because the finding is
reusable by anyone who reads this form later.

**15 of 44 dates carry more than one value per currency** with nothing to separate them. For USD
that could be resolved against the daily series already held — but for EUR, RUB, CNY and GBP there
is no independent daily series to disambiguate with, so it would mean guessing on a third of the
history. USD would add nothing anyway: the daily official rate is already the authoritative source.

### What was connected: transaction counts
`PAYMENTS_TOTAL_COUNT`, `PAYMENT_CARDS_COUNT`, `CASHLESS_PAYMENTS_COUNT`,
`CASH_WITHDRAWALS_COUNT` (formId=418, 71 months from 2020-01) and `REMITTANCES_SENT_COUNT`,
`REMITTANCES_RECEIVED_COUNT` (formId=412, 58 months from 2021-09).

The dataset held the corresponding **values** but no counts, and value alone cannot separate
people spending more from people transacting more often.

Cross-check against the value series on all 71 shared dates: a cashless payment averages
12,600–13,600 KZT through H1 2026, a cash withdrawal 113,000–123,000 KZT — withdrawals about
**nine times larger per transaction**, the expected shape, and confirmation that the two forms
share a date convention with no shift.

**The source's own Total does not always add up, and that is reported rather than enforced.**
Summing the ten instrument rows equals the published Total exactly on 66 of 71 months. On five —
2020-06, 2022-07, 2024-10, 2024-11, 2024-12 — the parts *exceed* the stated total, by 1,515 to
14,962 thousand transactions, with all ten instruments present. A hard guard would fail on real
published data, so this follows the `OIL_EXPORTS_VOLUME` precedent: check every run, print the
failing months to stderr, raise only if more than a tenth fail. **The published Total is what is
stored** — the parts are not summed to replace it. The separate card identity (cashless +
withdrawals = payment cards) does hold everywhere and is enforced as a hard guard.

Verified live: 142/142 NBK fetchers OK, 29/29 tests passing.

## 2026-09-02 — ARDFM added as a fifth agency; the banking block is unfrozen (393 indicators, 14,798 observations)

The audit's single remaining real defect is closed. `NPL_RATIO`, `CAPITAL_ADEQUACY_RATIO`,
`BANK_ROA`, `BANK_ROE` and `LOANS_TO_ECONOMY` had been stuck at 2024-04-01 since NBK `formId=314`
stopped updating, and the sweep of all 239 NBK forms confirmed no replacement existed there.
Banking supervision belongs to ARDFM, which publishes the figures **monthly**.

Nine indicators: `BANK_NPL_90_SHARE`, `BANK_NPL_90_AMOUNT`, `BANK_LOANS_TOTAL`,
`BANK_PROVISIONS_IFRS`, `BANK_CAPITAL_ADEQUACY_K1`, `BANK_CAPITAL_ADEQUACY_K2`,
`BANK_ROA_MONTHLY`, `BANK_ROE_MONTHLY`, `BANK_NET_INCOME`.

### Getting to the source
ARDFM has no API and finreg.kz no longer resolves. Its content sits behind the **same gov.kz
content-manager API that already serves Minfin**, under `projects=ardfm` — 2,700 documents. The
banking bulletin is located by the API's `title` filter, found by probing: the endpoint answers
400 naming the offending parameter for anything unsupported, so `q`, `search`, `name`, `text` and
`filter` were ruled out and `title` confirmed in a single pass. Documents are found by title, not
id, because each monthly edition is a new document.

The bulletins are **PDF**. pypdf extracts them cleanly and is now a dependency. `pdftotext` drops
every Cyrillic character on these files — it returns digits and Latin only, which looks like a
partially-working extraction rather than a failure.

### Three traps, all of which would have produced plausible wrong numbers rather than errors
1. **Every headline figure appears twice** — once in the narrative commentary, once in the table —
   and the two *disagree*, because the narrative rounds and compares against the same date a year
   earlier while the table compares against the start of the year. For ROA at 01.07.2026 the
   narrative reads "составило – 3,7% (4,6% на аналогичную дату)" and the table reads
   "4,21% 3,65%". The narrative comes **first**, so a first-match lookup silently takes the
   rounded figure on the wrong comparison basis. Every lookup is anchored to its table heading —
   and to that heading's *last* occurrence, because the contents page repeats "Таблица N." as a
   dotted line.
2. **The capital ratio labels nest**: `k1` is a prefix of `k1-2`, a different ratio on the next
   row (19.7% against 20.1%). Matched with a trailing space plus a column-count check.
3. **The row label must be stripped before parsing**, or the "90" in "свыше 90 дней" becomes part
   of the value. My first probe did exactly that, and also turned `k1 19,7%` into `119.7%`.

### The source contradicts itself on one row, and that is recorded rather than smoothed
`Провизии по МСФО` is printed **negative** in the 01.05 and 01.06.2026 editions and **positive**
in the 01.07.2026 edition, while the shared 01.01.2026 figure is 1,925.9 in both presentations.
It is a formatting change, not a data change, so the magnitude is stored and the sign discarded —
keeping it would have manufactured a swing of twice the value between two consecutive months.
I had written a note claiming a "sign-consistency guard" before implementing one; the note now
describes what the code actually does.

### Not spliced onto the frozen series
Different compiler, monthly rather than quarterly, definitions not verified to match. Levels are
consistent with where NBK left off — NPL 3.06% (2024-Q2) against 4.12% now, ROA 4.95% against
3.65%, ROE 31.7% against 24.14%, CAR 21.44% against k2 20.5% — which is reassuring but is not
grounds for joining them. `BANK_LOANS_TOTAL` differs by concept as well: loans to the economy
against all bank loans.

Three editions online, so these accumulate like the BNS publication-layer series.
Verified live: 9/9 ARDFM fetchers OK, 29/29 tests passing. Five agencies now:
NBK 9,037 observations, BNS 2,539, IMF 2,400, Minfin 795, ARDFM 27.

## 2026-09-02 — the rest of the ARDFM bulletin (404 indicators, 14,831 observations)

Eleven more series from the tables left unread in the first pass: balance sheet, deposits,
liquidity, and the sector's size relative to GDP. Two of them close audit items that NBK could
not answer.

- **`BANK_ASSETS_TOTAL`** — 74,226.8 bln KZT at 01.07.2026. This is the figure the audit asked
  for and NBK could not supply: `formId=1` lists 45 balance-sheet lines and publishes no total at
  all, `formId=60` returns seven unlabelled rows per bank-date. ARDFM publishes it outright.
- **`BANK_DEPOSITS_INDIVIDUALS_FX_SHARE`** — 20.2%, down from 21.8% at the start of the year. A
  **published** dollarization measure, where NBK's `formId=42` had the right currency dimension
  but ten unlabelled rows per date-currency. Household deposits only, so narrower than the audit
  asked — but published rather than constructed.
- `BANK_LOANS_TO_GDP` (27.3%) was listed in the audit as something to *derive*. The source
  publishes it directly, so nothing is computed.

Also: `BANK_ASSETS_GROSS`, `BANK_LIABILITIES_TOTAL`, `BANK_CLIENT_DEPOSITS`,
`BANK_DEPOSITS_LEGAL_ENTITIES`, `BANK_DEPOSITS_INDIVIDUALS`, `BANK_LIQUID_ASSETS`,
`BANK_ASSETS_TO_GDP`, `BANK_DEPOSITS_TO_GDP`.

### The asset rows are not in the table that names them
"Таблица 2. Структура совокупных активов" extracts as a heading and nothing else — its data is a
chart. The asset rows are in the document all the same, and fall inside **table 1's** span in
every edition. They are anchored there rather than to the heading that names them.

And the labels nest again, exactly like `k1`/`k1-2`: "Всего активы" is a prefix of "Всего активы
(без учета резервов (провизий))", and **both rows carry five numbers**, so the column-count check
cannot separate them. The net figure is matched with an explicit exclusion.

### A new cross-table identity, verified to fire
Tables 8 and 9 are compiled separately: table 9 splits client deposits into legal entities and
individuals, table 8 carries the total. They reconcile on all three editions — 19,581.9 + 28,586.4
= 48,168.3 exactly, 19,634.2 + 29,311.6 = 48,945.8 exactly, 20,579.9 + 30,136.2 = 50,716.1 against
a published 50,716.0, one rounding step. The guard was verified to **fire** when the
legal-entities lookup is pointed at the individuals row.

### Two things checked rather than assumed
The bulletin publishes **two** asset measures without saying which feeds its GDP ratio.
74,226.8 / 163,678.5 = 45.35% against a published 45.3%, while gross assets would give 46.7% — so
the ratio is built on **net** assets, and that is now recorded.

Gross assets minus IFRS provisions does **not** reproduce net assets: 70,901.9 against a published
70,774.1, a gap of about 120 bln at both dates. So provisions are not the only difference and
neither figure is derived from the other here.

### The column-date lookup had to be rewritten
In the 01.06.2026 edition a chart is extracted *ahead of* the table it belongs to, putting table
16's real header on line 33 of its span — counting lines from the top found nothing. The header
is now anchored to its own marker. A chart axis in the same span reads "01.01.26 01.02.26
01.03.26 01.04.2026 01.05.2026 01.06.2026", mixing two- and four-digit years; requiring four
digits rejects the short ones and the header anchor keeps the long ones out of range.

Verified live: 20/20 ARDFM fetchers OK, 29/29 tests passing.

## 2026-09-02 — loan quality by borrower segment, and concentration (414 indicators)

Ten more series from the ARDFM bulletin: tables 5, 6 and 7 (loan quality for corporate, retail
and SME borrowers), the share-capital line from the funding table, and table 15 (concentration).
The ARDFM block is now 30 indicators and the bulletin's substantive tables are read.

### The headline NPL rate is an average of divergent trends
The aggregate 90-day overdue share is 4.12%. Underneath it, at 01.07.2026:

| segment | book, bln KZT | 90+ overdue | year-to-date change in overdue amount |
|---|---|---|---|
| corporate | 6,428.2 | **2.0%** | −20.8% |
| SME | 12,172.8 | 3.9% | **+40.1%** |
| retail | 25,848.9 | **4.8%** | +15.8% |

Corporate credit is shrinking (−11.1% year-to-date) and its bad debt is falling. SME is the
fastest-growing book *and* the fastest-souring one. Retail is the largest book and carries the
highest bad-debt share, which is what pulls the headline up. None of that is visible in the
aggregate, which is the argument for taking the segments separately.

### The three segments do not sum to the total, and that is left alone
Corporate + retail + SME = 44,449.9 bln against a published `BANK_LOANS_TOTAL` of 44,754.2 — a
residual of about 304 bln, stable at 304–322 bln (~0.7%) across all three editions. Something
sits outside the three named categories and the bulletin does not say what. No identity is
asserted, nothing is derived from the difference, and the caveat is recorded on each segment so
nobody sums the three and reads the shortfall as an error.

### Concentration is the context for every aggregate here
The five largest banks hold 69.2% of assets, 72.7% of deposits and **75.8% of loans**. Lending is
the most concentrated of the three, so the segment NPL rates above are largely a statement about
five institutions rather than about a market.

### Share capital is a component, not equity
`BANK_SHARE_CAPITAL` (1,600.6 bln, 2.2% of funding) is paid-in capital only. The bulletin
publishes **no** balance-sheet equity total anywhere — which is why `BANK_LIABILITIES_TOTAL` has
no equity counterpart and why assets = liabilities + equity still cannot be checked. The funding
table also carries four numbers per row rather than the five of tables 4–8, and the column count
is asserted per row.

### Process note
I edited `config/indicators.yaml` and `update_ardfm.py` while a full five-agency run was in
flight. The running process had already imported its fetcher registry, so the new indicators
could not appear in that run's output — its result is a snapshot of the previous state, not of
this one. Verification was redone afterwards rather than read off a run that could not have
included the change.

Verified live: 30/30 ARDFM fetchers OK, 29/29 tests passing.

### A defect in my own module, found by the source refusing to talk to me
The first thirty-indicator run failed: gov.kz started refusing connections partway through, and
the pipeline correctly declined to rebuild the unified dataset. The cause was mine, not the
source's. Every indicator here is a separate fetcher and each one walks all listed editions, so
thirty indicators over three bulletins meant **ninety downloads of a ~450 KB PDF and ninety pypdf
parses per run** — about 40 MB, all of it the same three files.

Both are now cached per process. A fresh run still re-downloads, so the append-only raw archive
still records today's bytes, but within one run each document is fetched once and parsed once.
The first fetcher takes 31 seconds and the rest take about a tenth of a second each; the whole
module now runs in 26 seconds against a source that was previously being hammered.

Retries were added at the same time, covering `ConnectionError` and `Timeout` only — never an
HTTP status, for the same reason as the IMF module: a 404 or a 500 is information about the
source, and retrying it hides a real change behind a delay.

## 2026-09-03 — core inflation (418 indicators, 14,917 observations)

`CORE_CPI_YOY_EX3`, `CORE_CPI_QOQ_EX3`, `CORE_CPI_YOY_EX7`, `CORE_CPI_QOQ_EX7` from Taldau. The
audit listed core inflation as a monetary-sector gap and it had never been searched for.

**The source publishes two core baskets, not one** — and they are separate Taldau indexes rather
than two terms of one dimension. `55056856` excludes fruit, vegetables, petrol and coal;
`55056857` also excludes regulated utilities and rail transport. The parent index `703082`
("Базовый индекс потребительских цен") returns an empty segment list for every period tried, so
it is a catalogue heading, not a series.

### `periodId=5` is quarterly here, not monthly
This was the trap. Fourteen points span 2023-03-31 to 2026-06-30, and the period-on-period reading
is 102.6–103.2 — which as a *monthly* rate would annualise to about 36% and as a *quarterly* rate
to about 11%, matching the year-on-year reading of 111.4 on the same rows. Reading it as monthly
would have overstated inflation threefold while still looking like a perfectly plausible index.

### The chaining check settles three questions at once
Chaining four consecutive quarter-on-quarter indices reproduces the year-on-year index to within
±0.1 **across the entire history of both baskets**. That confirms the comparison terms are
correctly identified, that `periodId=5` really is quarterly, and that both comparison bases come
from the same underlying data. It is also the kind of check that could only pass if all three were
right, which is why it was worth running rather than asserting.

### An ordering worth noticing
Core ex-7 (111.9) reads **above** core ex-3 (111.4). Excluding administered prices *raises*
measured inflation, which says regulated utilities and rail transport were rising more slowly than
the rest of the basket. That is information, not noise.

Cross-checked against independently sourced headline series: `CPI_YOY` 112.6 for October 2025 and
the NBK-sourced `ANNUAL_INFLATION` falling from 12.2% in February 2026 to 10.2% by August. Core
sitting just below headline is the expected relationship.

### Two of the four unsearched indicators are not statistical series
- **Minimum wage** — zero results in Taldau under three wordings. Expected on reflection: it is a
  *legislated* figure set annually in the republican budget law, not a statistical observation, so
  it does not belong to a statistics catalogue. It would have to come from legal text, which is a
  different kind of source from everything else here.
- **Grain harvest** — "валовой сбор зерна" returns nothing; "валовый сбор" returns three indexes,
  all of them about **flowers**. "зерновых культур" returns twenty, but they are stocks held,
  receipts and inter-regional purchases rather than the harvest. Recorded as *not found* rather
  than *not published*: this was a keyword search against the catalogue, which is weaker evidence
  than the structural probes used elsewhere.

Verified live: 133/133 BNS fetchers OK, 29/29 tests passing.

## 2026-09-03 — wages by economic activity (430 indicators, 14,929 observations)

Twelve series — average wage and real wage index for mining, manufacturing, agriculture,
construction, finance and education — from **the same sheet that already supplied
`AVG_WAGE_QUARTERLY`**. That fetcher read the `Всего` row; twenty more sit below it, one per
activity. This is the fourth time in this project that a gap turned out to be inside a source
already connected.

### The aggregate hides a four-to-one spread

| activity | wage, KZT | real index |
|---|---|---|
| mining and quarrying | 1,020,632 | 99.1 |
| finance and insurance | 941,411 | 104.6 |
| manufacturing | 508,854 | 103.2 |
| **national average** | **445,068** | **99.8** |
| construction | 427,282 | 99.3 |
| education | 315,100 | **93.3** |
| agriculture | 268,096 | **107.5** |

### The real index is where the sector detail earns its place
It moves in *opposite directions* across activities while the national figure sits still:
education 93.3 and arts 93.1 against administrative services 111.6 and transport 104.6, with the
aggregate at 99.8. Public-sector real pay was falling while private services rose — and
`REAL_WAGE_INDEX_QUARTERLY` shows neither. Two more pairings worth noting: mining pays the most
and its real pay was *falling*; agriculture pays the least and had the strongest real gain.
Construction volumes grew 15.3% year on year while real pay in the sector did not.

Six activities were taken rather than all twenty-one — they span the wage distribution and the
public/private divide, which is what the aggregate cannot show. The rest are on the same sheet
with the same lookup. Rows are matched exactly rather than by prefix, since "Горнодобывающая
промышленность и разработка карьеров" and "Обрабатывающая промышленность" end in the same word.

### ARDFM's other sector bulletins are discontinued
Checked by title: pension latest 01.12.2020, securities market 01.10.2011, non-banking 01.04.2024,
microfinance 2023, insurance 2005–2011 with no dated editions. Searching for current replacements
returned only regulatory acts. Only the banking bulletin is maintained.

### A correction to my own method
I first reported "3,200 ARDFM documents, none updated in 2026". **That was false** — the banking
bulletins carry 2026 update dates. The `projects=ardfm` pagination is broken: pages 0 and 1 come
back identical, 500 unique ids out of 600 fetched, and the ordering reaches 2008–2010 by page 5
without surfacing recent items. No sort parameter is accepted. The title filter is the only
reliable access path, so absence found by paging that endpoint is not evidence of anything, and
the scope note now says so.

Verified live: 145/145 BNS fetchers OK, 29/29 tests passing.

## 2026-09-03 — CPI moved to a live channel; a date-convention defect found and fixed

A request to delete the 18 "stale" indicators turned into a review, because the flag was mine and
deserved checking before anything was deleted. Three of the eighteen were false positives and the
review found three defects in work shipped earlier the same day.

### CPI had not stopped; its delivery channel had
Open-data element 1549 ends at October 2025 — confirmed by downloading the 6 MB file and reading
its own `PERIOD` column, so the source and not the fetcher. Taldau index 703076 carries the same
series through July 2026.

**The switch was checked before it was made.** Across all 178 overlapping months, for all three
comparison bases, cube and Taldau agree to within 0.05 index points — zero discrepancies, same
start (2011-01), nine more months. That is a channel that stopped, not a series that ended, and it
is the difference between repointing and replacing. `CPI`, `CPI_YOY` and `CPI_YTD` now come from
Taldau; 178 → 187 points each.

### Three defects in my own recent work
1. **Core inflation was connected quarterly when monthly exists.** `periodId=4` is monthly and `5`
   is quarterly; I used 5 and got 14 points where 42 were available. Fixed, and
   `CORE_CPI_QOQ_*` renamed to `CORE_CPI_MOM_*` — "quarter-on-quarter" had become wrong.
2. **The Taldau manifest reported `annual` for every series** regardless of period, which was
   simply false for the quarterly and monthly ones. Frequency is now derived from `period_id`.
3. **`BASE_RATE` was declared daily** while its own fetcher note said "event-dated … not literal
   daily observations". Actual spacing is 49 days — MPC meetings. Corrected to `irregular` rather
   than loosening the staleness threshold to fit a wrong label.

### The date-convention defect, and how far it reached
Moving CPI to Taldau changed its dates from month-**start** to month-**end**, because the Taldau
helper stamped every frequency at period end. That silently broke every join between CPI and the
monthly production, trade and labour series. **A join that returns nothing raises nothing** — it
had to be found by looking, and it was found by counting conventions rather than by any test.

Checking the rest showed the problem was wider than the change that exposed it: 113 of 125 monthly
series used month-start, 12 used month-end, and five of those twelve were mine from earlier in the
session (the two trade price indices) or the IMF module's (`OIL_PRICE` and two commodity
terms-of-trade series). All monthly series are now on month-start — **125 of 125**. `CPI_YOY` and
`OIL_PRICE` now share 187 dates; they shared none.

Quarterly and annual carry the same split (82 start / 40 end, and 35 start / 120 end). That is
pre-existing and was **not** touched — changing 75 series on a convention question is the user's
call, not a side effect of a CPI fix.

### Where the staleness count landed
18 → 14. The remaining fourteen are the cases where the replacement is genuinely shorter than the
original, and the recommendation is unchanged: mark them superseded rather than delete. Deleting
`IND_PROD` (15 points from 2009) to keep `INDUSTRIAL_PRODUCTION_INDEX` (4 points from 2026) trades
years of history for months, and the ARDFM banking series explicitly cannot be spliced onto the
NBK ones they replace.

Verified live: 430/430 indicators OK in a clean full run, 29/29 tests.

## 2026-09-03 — lifecycle marks instead of deletion

The 14 remaining flagged series are marked rather than deleted, plus `FREIGHT_TURNOVER` which is
superseded without being stale — those are different properties and the marks now say which.

Three statuses instead of one, because lumping them would have hidden the distinction that
matters:

| status | count | meaning |
|---|---|---|
| `superseded` | 5 | a replacement is connected and **reconciles** with the original |
| `superseded_not_spliceable` | 6 | a replacement exists but the two **must not be joined** |
| `stale_source` | 4 | no replacement; the publisher is simply behind |

The middle category is the one worth having. Five of its six are the NBK banking series replaced
by ARDFM ones: different compiler, monthly rather than quarterly, definitions not verified to
match, and for `LOANS_TO_ECONOMY` a different concept as well (loans to the economy against all
bank loans). The sixth is `PASSENGER_TURNOVER`, where the monthly series is **not** a continuation
— 266.8 bn p-km here against about 94 bn annualised there, while freight from the same source
reconciles almost exactly, so it is not a units error and remains unexplained.

Each mark carries `superseded_by` and a one-line reason in `lifecycle_note`, so the reason travels
with the data rather than living only in this log.

**Why not delete.** The replacements are shorter than the originals by a wide margin: `IND_PROD`
has 15 points from 2009 against 4 in the monthly index from 2026; the five NBK banking series have
18 points from 2020 against 3 in the ARDFM ones. Deleting would trade years of history for months,
and for the six not-spliceable cases it would not even produce a continuous series.

The catalogue artifact was rebuilt on the new numbers (15,072 observations) with a status column,
a "only marked" filter, and the reason on hover.

## 2026-09-03 — observation type as a field, and the date convention derived from it

A note from the user: an indicator can be measured **as at a date** (1 January 2026) or **over a
period** (January–March 2026), comparisons run year-on-year, quarter-on-quarter, month-on-month or
date-against-the-same-date, and the source states which. None of that was recorded anywhere in the
dataset — and I had already been stopped by exactly this distinction, then worked around it.

`TAX_ARREARS_TOTAL` is недоимка, a **stock** read "as at" its date. `PENSION_CONTRIBUTIONS_RECEIVED`
sits on the same sheet with the same date and is поступления, a **flow** over a year. That is why
annual dates were left alone in the convention sweep. The right answer was not "leave it" — it was
"record what the number is".

### The information cannot be recovered from prose
An automated pass over `sources.yaml` notes classified 51 indicators. On manual review roughly
**thirty were wrong**. The exchange rate for the yuan and the National Fund stabilisation portfolio
were filed as "year-to-date" because that phrase appears in their notes describing something else
in the same table; `RETAIL_TRADE_MONTHLY` was filed as cumulative even though its own note says
"single month (not cumulative)". Three index series were filed as totals.

So the field is populated **only from source documents read directly**, and every entry carries the
evidence: "сноска: среднегодовые за 12 месяцев", "обложка: Январь-июль 2026 года", "колонка 2:
отдельный месяц".

| `observation_type` | count | meaning |
|---|---|---|
| `point_in_time` | 28 | a stock or rate **as at** the date |
| `period_total` | 23 | a flow **over** the period — 7 of them `cumulation: year_to_date` |
| `period_average` | 20 | an average over the period |
| `comparison_index` | 21 | the value **is** a comparison between two periods |

**92 of 430.** The other 338 carry no type at all — a visible, tracked gap rather than a silent
default. Filling it means re-reading each source, which is the only way it can be filled honestly.

### The type now drives the date convention
`point_in_time` series are exempt from normalisation: their date **is** the measurement, and a
balance at 30 June is not a balance at 1 June. That settles the annual question on the merits
instead of by majority vote, and it is why `lib/periods.py` takes the type as an argument.

### Two duplicates fell out
`EXPORT_PRICE_INDEX` and `IMPORT_PRICE_INDEX` each held June 2026 **twice** — 127.8 at both
2026-06-01 and 2026-06-30 — a duplicate created by my own partial fix, where the fetcher had moved
to month-start while the stored file still held month-end and the accumulate merge kept both. Same
value, so nothing was lost; the count fell from 15,072 to 15,070 because two duplicates went away.

Verified live: 430/430 in a clean full run, zero convention warnings, 29/29 tests.

### Still only in prose
The comparison basis of the 21 index series — year-on-year, month-on-month, against December —
lives in the note and the unit string. That is the next field of the same kind.

## 2026-09-03 — observation type from source metadata, not prose (163 of 430)

Continues the pass begun above, and changes how it's done: everything from here on cites the source
statement it came from, not a note written earlier in the project.

The IMF batch (28) comes from the official WEO codelist, fetched from the SDMX structure endpoint.
The names state the answer outright: `PCPIE` is "End-of-period", `PCPI` is "Period average",
`NGDP_RPCH` is "Percent change", "Gross debt" is a stock. Three indicators whose names don't say —
the GDP deflator, the PPP conversion rate, the unemployment rate — are left unclassified rather than
assumed.

The Taldau batch (43) comes from the methodological passport each index publishes, carrying
"Определение показателя" and "Методика расчета". Classifying from those is reading the source; a
first attempt classified from prose notes written earlier in the project and got roughly thirty of
fifty-one wrong.

The passport rules needed two rounds. The first ordering sent `COMPUTERS_IN_ORGANIZATIONS` to
`period_total` on the phrase "за отчетный период", when its own definition says the computers are
those "находившиеся на балансе" — a stock; `DOCTORS_TOTAL` the same way, on "в среднем за год". That
phrase describes the reporting period, not the nature of the quantity, so the specific wordings run
first now.

A fifth type, `period_ratio`, is added for series like "% of GDP" and rates per 1000 population —
neither summable across periods nor a stock at a date. 23 series are that shape.

**163 of 430.** 267 remain, concentrated in NBK (130) and Minfin (79). 29/29 tests.

## 2026-09-03 — NBK observation types from pinned fields and form names (251 of 430)

Two kinds of evidence for NBK. The strongest is the value the fetcher already pins: several forms
state the answer outright — "Stocks (mln. tenge)", "Balance (mln. tenge)", "mln. of KZT, end of
period", "Transactions volume", "Average rate - bid". Where that's absent, the form name from the
API's own category tree settles it where the concept is unambiguous: external debt and the
international investment position are positions by definition; KASE trade results and remittance
amounts are turnover.

Three corrections, each the same mistake in a different guise — a rule matching the container rather
than the quantity:

`EXCHANGE_RATE_CNY_KASE` nearly went to `period_total` because its form is "Results of trades on
KASE", which carries both turnover and rates. The unit is now checked before the form name, so a
rate can never again be classified from its form's title.

Reading only the `type` field missed the reserve series, whose decisive phrase sits in `code`:
"Reserve assets + Foreign assets of the National Fund, end of period". All pinned fields are searched
now, not just `type`.

`RESERVES_IMPORT_COVER` and `RESERVES_AND_NF_IMPORT_COVER` are the same concept on different forms
and were landing on different types. Import cover is a stock expressed in months, so the unit decides
it now, not the form.

**251 of 430.** 179 remain: Minfin 79, BNS 52, NBK the rest. 29/29 tests.

## 2026-09-03 — Minfin observation types (330 of 430)

Three kinds of evidence already sitting in the repository — none of it a guess about what a name
implies.

Twenty-three settled by the unit string itself, already reading "million KZT, year-to-date
cumulative" or "million KZT, flow during the quarter" from when the sheet's column header was first
read. Twelve debt series settled by notes recorded at the time of reading the source, stating
point-in-time outright — `GOV_ACCOUNTS_PAYABLE` and `GOV_ACCOUNTS_RECEIVABLE` follow from their own
notes: creditor and debtor arrears are balances, not flows.

The remaining budget series were settled empirically. `GOV_EXPENDITURE`, `TAX_REVENUE` and their
siblings hold exactly one observation per calendar year at a plausible annual magnitude — 25 trillion
KZT of expenditure in 2025 — so they're annual totals, not year-to-date figures that happen to be
sampled in December. The National Fund portfolio series are quarter-end holdings from a sheet dumped
earlier that carries only portfolio composition.

**330 of 430.** 100 remain: BNS 52, NBK 42, IMF 6. 29/29 tests.

## 2026-09-03 — BNS observation types (370 of 430)

Two sources: the Taldau passport already fetched during the earlier pass — most of these indicators
were in that pass's skip list because they didn't match its rules, not because evidence was missing
— and the fetch-investigation notes already in `sources.yaml`.

Explicit period wording carried most of it. `GRADUATES_HIRED`: hired "в отчетном периоде".
`CAPITAL_CONSUMPTION`: value decline "в течение отчетного периода". `EMPLOYED_TOTAL`: LFS
reference-week methodology, "в течение определенного короткого периода, равного одной неделе" — the
same evidentiary basis already used for the quarterly labour-survey indicators. The System of
National Accounts family (`GFCF`, `GROSS_OUTPUT`, `GROSS_ACCUMULATION`, `INTERMEDIATE_CONSUMPTION`,
`COMPENSATION_EMPLOYEES`, `AGRICULTURE_OUTPUT`, business and tourism value-added) are
production-account flow concepts by SNA definition — output and value added are inherently measured
over an accounting period, not stocks at a date.

`GDP_NOMINAL` stands out: its `json_cube` response carries periods literally named "Январь-Март",
"Январь-Июнь" — evidence of year-to-date cumulation visible in the response structure itself, not in
a prose note.

Twelve indicators were left deliberately unclassified here for the first time — the same twelve that
"добей последние 13" would later chase down to nine. Their processing-method field says only "данные
выборочной совокупности распространены на генеральную совокупность" (sample data scaled to the
population), which describes how the estimate was produced, not when it applies. Not evidence of
stock vs. flow vs. average, so no rule fires: `HOSPITAL_BEDS`, `ICT_SPECIALISTS`,
`ORGANIZATIONS_USING_COMPUTERS`, `COMPUTERS_INTERNET_CONNECTED`, `WORKERS_USING_COMPUTERS`,
`WORKERS_USING_INTERNET`, `ELECTRICITY_PRODUCTION`, `ENERGY_CONSUMPTION`, `ECOMMERCE_SERVICES_VALUE`,
`TOTAL_FERTILITY_RATE`, `POVERTY_HEADCOUNT`, `TOURISM_EMPLOYMENT`.

**370 of 430.** 60 remain: NBK 42, BNS 12, IMF 6. 145/145 BNS fetchers live, 29/29 tests.

## 2026-09-03 — final NBK batch (411 of 430)

41 of the last 42 NBK indicators, closing all but one gap in the agency. Three kinds of evidence not
used in earlier batches.

A verified identity as evidence: `CURRENT_ACCOUNT_BALANCE` is `period_total` not from its form or
unit, but because this session had already proved goods + services + primary + secondary income (all
`period_total` flows) sum to it within 0.01 across 105 quarters. If the parts are flows, the sum is a
flow.

A form name stating its own construction, quoted rather than inferred: `FDI_NET_INFLOW`'s form is
titled "Direct investments ... flows for the period". `DEPOSIT_RATE` and `LENDING_RATE` come from
forms literally named "Средневзвешенные ставки" (weighted-average rates). `ENTERPRISE_DEBT_BURDEN`
and `CAPACITY_UTILIZATION` carry `indicator_code` values of "Average debt burden" and "Capacity
utilization - Weighted Average" — the source's own field.

A field within one form that differs from its siblings: `PENSION_FUND_ASSETS` matches
`class_type='Pension savings'`, an accumulated stock, distinct from the receipts/disposals flow rows
the same form also carries. Reading only the form name would have missed this.

Twelve diffusion indices (0–100, 50 = neutral) from the NBK Enterprise Monitoring business survey are
`period_average` as the standard, internationally-defined construction of that statistic — a
net-balance reading representing the survey period, not a comparison between two periods.

`INFLATION_EXPECTATIONS` is the one left unclassified: a survey percentage that's neither a stock nor
a summable flow, with no source text confirming whether it's reported as a mean, median, or something
else.

**411 of 430.** 19 remain: BNS 12, IMF 6, NBK 1. 142/142 NBK fetchers live, 29/29 tests.

## 2026-09-03 — final IMF batch (416 of 430)

Five of the last six IMF indicators, from a codelist not checked in the earlier WEO pass. `CTOT`
(commodity terms of trade) describes its own indicator as "June 2012 = 100" — a fixed-base index,
`comparison_index` by that explicit construction, same base for both the standard and fixed-weights
variants.

`IMF_GDP_DEFLATOR_INDEX`: the WEO codelist description groups the GDP deflator explicitly alongside
"producer or consumer price indices" as the implicit counterpart to those explicit ones — classified
`comparison_index` on that basis rather than `period_ratio`, since the source frames it as the same
family as CPI/PPI.

`OIL_PRICE`: APSP is named "Average Petroleum Spot Price" and documented as "the simple average of
Brent, Dubai Fateh and WTI" — `period_average`, directly from the name and the fetcher's own
docstring.

`IMF_UNEMPLOYMENT`: WEO's own description frames it as a bare ratio (unemployed / labor force), but
Kazakhstan's unemployment rate is compiled by BNS using LFS reference-week methodology, already
confirmed as the basis for the equivalent national series (`period_average`). Classified consistently
with that traced national methodology rather than the IMF cross-country boilerplate.

`IMF_PPP_EXCHANGE_RATE` stays unclassified: its codelist description is generic boilerplate that
doesn't settle stock vs. average.

**416 of 430.** 17 remain: BNS 12, NBK 1, IMF 1. 34/34 IMF fetchers live, 29/29 tests.

## 2026-09-03 — INFLATION_EXPECTATIONS closes NBK; IMF_PPP_EXCHANGE_RATE confirmed at its limit (417 of 430)

`INFLATION_EXPECTATIONS` found via a channel not checked before: the NBK form metadata endpoint (a
different API surface from the Taldau passport mechanism used for the BNS batches) states the source
outright — "results of the households survey on inflationary expectations", Данные=Aggregated. Same
evidentiary basis already used for the Enterprise Monitoring diffusion indices: a survey statistic
representing its period. Closes NBK except for the one indicator that genuinely lacks evidence.

`IMF_PPP_EXCHANGE_RATE` was checked one level deeper before giving up on it: the raw WEO CSV carries
a `STATISTICAL_MEASURES` column, empty for every other indicator in this project but populated "RT"
for this one. Decoded via the SDMX codelist, RT is "Rate: A measure that expresses the frequency of
occurrence of an event... in relation to another quantity" — the exact same generic boilerplate
already seen, and rejected as decisive, for `IMF_UNEMPLOYMENT`'s `LUR` code. Confirmed rather than
assumed that there is nothing more specific to read.

The 12 remaining BNS indicators were re-verified exhaustively rather than left as a known gap: every
field of every Taldau passport was searched for time-marker wording this time, not just the six
fields checked in the earlier batches. One match came back, and it was spurious — "накоплен" inside
an unrelated department name ("Управление счетов накопления"), not evidence about the indicator
itself. The 12 stand confirmed as lacking source evidence, not merely unexamined.

**417 of 430.** 13 remain: BNS 12, IMF 1. 142/142 NBK fetchers live, 29/29 tests.

## 2026-09-03 — comparison basis for all 44 comparison_index indicators, and a three-year-old misclassification caught

Same discipline as `observation_type`: what basis a comparison index compares against — year-on-year,
month-on-month, a year-to-date base, or a fixed historical base — becomes a queryable field instead
of living only in prose.

Most of the 44 already carried the answer in their own unit string, written when the indicator was
connected and verified live: "same month previous year = 100" is `yoy`, "previous month = 100" is
`mom`, "December of previous year = 100" is `ytd_base`. For annual-frequency series worded "% change
vs previous period", the basis follows from the frequency itself — at annual frequency, "previous
period" is definitionally "previous year".

Four indicators carried only a bare "index" unit and needed a live check of the raw data rather than
a guess from the label. `NEER` and `REER`: the value hits exactly 100.0 at 2016-12-01, and only
there, across all three variants of the same NBK form (nominal, real, real effective) — not a
coincidental near-100 reading but a genuine rebase point. `IMF_GDP_DEFLATOR_INDEX`: exactly 100.0 in
2005. Both `fixed_base`, with the base date now recorded in `comparison_basis_evidence`.

The fourth, `BUSINESS_ACTIVITY_INDEX`, turned out to be misclassified from the very first NBK batch,
months earlier in the project: it had matched the generic `^index` unit rule as `comparison_index`
without anyone checking what the data actually does. The live check shows a range of 36.4–51.7
clustered around 50 — a diffusion index (50 = neutral), not a fixed-base index — and its form sits in
the same "Survey Results → Enterprise Monitoring" category as the twelve diffusion indices already
classified `period_average`. Corrected. This is the same failure mode already hit and fixed three
times in this project — a rule matching the container label rather than the quantity's actual
behaviour — caught this time only because the data was checked before the classification was trusted.

**430 indicators, 15,071 observations, 417 with `observation_type`, 44 with `comparison_basis`.**
142/142 NBK fetchers live, 29/29 tests.

## 2026-09-03 — the last 13: four more resolved via a new source, nine confirmed at the limit

Thirteen indicators had no source text specific enough to classify: 12 from BNS, one from IMF
(`IMF_PPP_EXCHANGE_RATE` — checked against every structural column the SDMX dataflow carries,
including `STATISTICAL_MEASURES`, down to a `RT` code that decodes only as generic "Rate", the same
dead end already hit for `IMF_UNEMPLOYMENT`'s `LUR`). Told to close them, the right move was not to
re-read what had already come up empty — it was to find sources not yet checked. `stat.gov.kz` turns
out to publish its approved methodologies at `/ru/methodology/`, indexed by topic, each document
carrying an approval date and registration number. That was new this session.

Four indicators resolved:

- **`POVERTY_HEADCOUNT`** — the poverty methodology document: built on ВОДХ, the household
  living-standards sample survey, and "Уровень бедности рассчитывается на квартальной и годовой
  основе". Same survey underlies `GINI_COEFFICIENT` and `POVERTY_DEPTH`, already `period_average`.
- **`TOTAL_FERTILITY_RATE`** — the fertility-indicators methodology: the total fertility rate
  "характеризует среднее число детей, рожденных одной женщиной... при условии сохранения
  интенсивности повозрастной рождаемости за расчетный год" — an explicit average, built from one
  calendar year's age-specific rates.
- **`ELECTRICITY_PRODUCTION`** and **`ENERGY_CONSUMPTION`** — the fuel-energy balance methodology
  states the balance as an identity: "Общее первичное потребление энергии и ее эквивалентов =
  статья 1.1 (производство) + статья 1.2 (импорт) – статья 1.3 (экспорт) – статья 1.4 (бункеровка)
  – статья 1.5 (изменение запасов)". Production and consumption are both terms in a sum of period
  flows — the same construction already used for `CURRENT_ACCOUNT_BALANCE` — and the balance keeps
  stocks (запасы, "at start/end of year") as a separate, explicitly labelled line, not mixed in.

Nine stayed unclassified, now confirmed rather than merely unchecked:

- `ORGANIZATIONS_USING_COMPUTERS`, `COMPUTERS_INTERNET_CONNECTED`, `WORKERS_USING_COMPUTERS`,
  `WORKERS_USING_INTERNET` all trace to the same BNS annual ICT-in-organizations survey (the English
  name "Workers Using a Computer **at Work**" rules out the household survey as the source). The
  methodology document says only "проводится на годовой основе выборочным методом" — that is
  cadence, how often the survey runs, not a reference-period statement of what the number represents.
  The household side of the same document *does* carry real reference-period language ("последним
  трем месяцам, предшествующих интервью"), which is exactly why it would have been a mistake to
  borrow it here — it describes a different survey.
- `ICT_SPECIALISTS` and `ECOMMERCE_SERVICES_VALUE` — the same ICT methodology never uses
  "специалист" or "работник", and never describes an own-site sales concept; zero occurrences,
  not weak ones.
- `TOURISM_EMPLOYMENT` — both tourism methodology documents read in full, including one approved
  31.07.2026 that BNS has not used before this archive search (mobile-positioning-based visitor
  counting). Neither touches employment; the newer one is entirely about identifying trips from
  telecom signalling data.
- `HOSPITAL_BEDS` — the methodology archive has no health or medicine section at all.

**421 of 430.** Verified: 29/29 tests, BNS live fetch clean.

## 2026-09-03 — cumulation stops lying to the outlier check

`observation_type` and `comparison_basis` had a real consumer already sitting in the pipeline, not a
hypothetical one: `validate_outliers` compares each observation to the one before it and warns past a
50% swing. Nobody had told it that 34 indicators are `cumulation: year_to_date` — a value that is
*supposed* to climb through the year and drop back at every January reset. Every one of those resets
was going through as a false "jump".

`GDP_NOMINAL` in this run's own report: ~60 warnings, one for nearly every quarter boundary since
2010, each one just the source's own accounting doing what year-to-date accounting does — 34.1
trillion in January, 70.9 trillion in April is not the economy grabbing +108% in a quarter, it's Q1
plus Q2 sitting next to Q1 alone.

The check now takes `cumulation` and, for `year_to_date` series, compares each observation's *own
-period contribution* — itself minus the previous observation in the same calendar year, reset at the
year's first observation — instead of the raw cumulative total. Wired through the one place all five
agencies already read indicator metadata (`_meta = _indicator_meta(...)`) into the one place they all
call `validation.run_all`, so the fix is a single line in each orchestrator.

`GDP_NOMINAL` live: 60 warnings to 5. The 5 that remain are real and worth having: every one is a
Q3-to-Q4 step, 50-59%, recurring nearly every year since 2019 — Kazakhstan's Q4 nominal GDP genuinely
running well above Q3, not a reset artifact. Three tests lock the behaviour in: a plain series still
flags a real jump, a YTD series's January reset produces zero warnings, and a genuine mid-year spike
in a YTD series is still caught (proving the fix retargets the check rather than disabling it).

Minfin's YTD budget series (`CUSTOMS_DUTIES`, `PROPERTY_TAX`, `GOV_WAGES_EXPENDITURE` and others, 23
of the 34 total) still carry real warning counts after the fix — checked `CUSTOMS_DUTIES` directly:
April and May 2025 are simply absent from the stored data, so the March-to-June step is genuinely
three months of contribution next to the one-month step that follows it. That is a pre-existing gap
in what the source publishes, not something `cumulation` was ever positioned to fix, and it is left
alone here.

Verified live across all four agencies that carry a `year_to_date` series — BNS (145/145), Minfin
(79/79), NBK (142/142), ARDFM (30/30) — plus a clean import of `update_imf.py`, whose edit is a
provable no-op: IMF carries zero `year_to_date` indicators. 32/32 tests (29 plus the three new).

## 2026-09-04 — this folder had not been current since 2026-09-01

`build_project_knowledge.py` regenerates `DATA_CATALOG.md`, `DATA_DICTIONARY.md`, `SOURCES.md` and
`latest/{macro_latest.csv,macro_metadata.json}` — the only files that reach the Claude Project
"Экономика Казахстана" once someone clicks Sync now. Its own docstring says to run it after
`update_all.py`. Nothing ever called it: not `update_all.py`, whose own docstring lists "refresh
metadata/project_knowledge" as one of its steps and then doesn't do it, and not the CI workflow,
which only calls `update_all.py`. Every file in this folder except this log — the one file edited by
hand all session — carried a 2026-09-01 timestamp while the repository moved from 342 indicators to
430, gained the entire `observation_type`/`comparison_basis`/`cumulation` field system, and added a
fifth agency. None of that had reached the folder this pipeline exists to keep current.

`SOURCES.md` is the clearest proof: it listed four agencies. ARDFM — added 2026-09-02, 30 indicators
— had no row, because nothing had regenerated the file since before ARDFM existed.

Fixed by calling `build_project_knowledge.main()` from `update_all.py`, placed after the test gate
passes and before the run report is written — so a run that fails validation or tests leaves this
folder at its last known-good state rather than publishing something broken, which is also why the
call is a direct one, not wrapped in try/except: a failure here should stop the run loudly, the same
as everywhere else in this pipeline. Regenerated now by hand to catch up immediately rather than
waiting for tomorrow's scheduled run: **430/430 connected**, `SOURCES.md` now lists five agencies.

Also dropped a hardcoded "Stage 1 (15-20 indicator pilot)" from the catalog's own title — the count at
the bottom of the file is generated from the real total already: no reason for the title to freeze a
number the moment it was written. Same staleness, smaller instance: `README.md` still said "four
sources," "18 pilot indicators," and listed `{bns,nbk,minfin,imf}` in the repository layout with
ARDFM absent from all three. Corrected to the current counts.

**Known gap, not fixed here:** `DATA_DICTIONARY.md`'s per-indicator entries come from
`metadata/{agency}/{id}.json` — source, unit, frequency, period, methodology, transformation,
revision status — and that file has no `observation_type`, `comparison_basis`, or `cumulation` field.
The dictionary synced into the Project still can't tell a reader whether a value is a stock, a flow,
or a comparison already, or what a comparison is measured against. The metadata this session built
specifically to answer that question lives in `config/indicators.yaml`, which this generator doesn't
read from at all.

## 2026-09-04 — the deferred phase starts: a curated correlation pass

Both `README.md` ("No econometric modeling yet") and `project_knowledge/README.md`
("Modeling is a deliberate later phase") named this and put it off until the dataset
itself was solid. Told to start it, "just compute correlations" was the wrong first
move: the project has a strict, consistently-enforced rule against publishing an
aggregate a source doesn't itself publish, and two real landmines in the data make a
naive correlation wrong outright -- annual dates are deliberately left on mixed
period-start/period-end convention across indicators (`scripts/lib/periods.py`), and
34 indicators are year-to-date-cumulative, where a raw January-to-December comparison
reads a normal reset as a collapse.

Two background research passes and one design pass went into this before any code, and
the design itself surfaced two pieces of already-written, already-tested, completely
unused infrastructure: `scripts/lib/transformations.py` (yoy/qoq/mom/growth_rate/
deflate/rebase_index, docstring'd with exact formulas, called by nothing outside its
own test file) and `config/frequency.yaml` (per-indicator cross-frequency aggregation
rules -- `EXCHANGE_RATE: mean`, `GOV_REVENUE: sum`, `M2: end_of_period` -- read by no
code anywhere). This phase is what finally wires both in, rather than reinventing
either.

**What shipped**, a first slice, deliberately small:

- `transformations.decumulate_ytd` -- the one real gap in that module. Converts a
  year-to-date cumulative series to its own-period contribution (same logic
  `validate_outliers` already computes inline for the outlier check, now reusable for
  anything that needs the de-cumulated series itself). Tested against the exact
  fixtures already proven correct in `test_schema.py`'s YTD outlier tests, so the new
  reusable version is checked against already-correct behaviour, not a fresh guess.
- `scripts/analysis/` (`pairs.py`, `correlate.py`, `report.py`) + `scripts/
  analyze_correlations.py` -- a manually-run script (not wired into `update_all.py` or
  CI) that correlates 6 hand-picked pairs from `data/unified/macro_long.csv`: headline
  vs core inflation, oil price vs USD/KZT, REER/NEER vs CPI, government revenue vs
  expenditure, oil price vs crude export value. Every pair carries a written rationale
  (why it was picked) and interpretation (what to weigh while reading the result) --
  both human-authored in `pairs.py`, not generated, since a script narrating its own
  economic story would be exactly the kind of unearned confidence this project has
  avoided everywhere else.
- Four guardrails that refuse rather than guess: an indicator carrying a `lifecycle`
  flag (a known structural break) is rejected unless explicitly acknowledged in
  `pairs.ACKNOWLEDGED_LIFECYCLE`; an IMF `international_projection` series (WEO
  forecasts through 2031 baked into the same column as actuals) is rejected unless
  `pairs.FORECAST_CUTOFF_YEAR` states the last real year; a cross-frequency pair with
  no entry in `config/frequency.yaml`'s aggregation rules is rejected rather than
  assigned a guessed method; two annual series with different date conventions are
  rejected rather than silently joined on the wrong year-anchor.
- Output lives under a new top-level `analysis/` -- deliberately not `data/processed/`,
  `config/indicators.yaml`, or `project_knowledge/` -- so nothing computed here can be
  mistaken for a connected, source-published indicator. `analysis/README.md` states
  this up front, in the same register as `project_knowledge/README.md`'s "what NOT to
  expect here," and lists the full candidate set including what was left out of v1 and
  why (`UNEMPLOYMENT` vs wages: only 10 points, source stopped mid-2025 -- too weak to
  lead with).

**Verified, not assumed**: two of the six results (`GOV_REVENUE`/`GOV_EXPENDITURE`
r=0.904 n=11; `OIL_PRICE`/`EXCHANGE_RATE` r=0.063 n=62) were computed independently by
hand against the live repo before being written into the plan, then reproduced exactly
by the finished script. `OIL_PRICE` vs `EXCHANGE_RATE` is worth reading in full as an
example of the standard this output holds itself to: r=0.063 is reported as a real,
checked near-zero result over 2021-2026, explicitly followed by why that is not the
same claim as "oil doesn't matter to the tenge" (NBK manages the rate rather than
floating it; monthly averaging blurs timing; the window spans very different regimes).

13/13 relevant new tests (53/53 total), `git status` confirms nothing outside
`analysis/`, `scripts/`, and `tests/` changed -- no new dependency, `pandas` already
covered it.

Deliberately out of scope: seasonal decomposition and forecasting (both need
`statsmodels`; forecasting additionally risks the WEO-contamination problem above),
statistical significance testing (needs `scipy`), any all-pairs matrix, and syncing
this output into `project_knowledge/`/the Claude Project -- an explicit follow-up
decision once this output's shape has been reviewed, not bundled in here.

## 2026-09-04 — two more correlation pairs, one of them a direct test of the other

Added the two v1.1 candidates already named and deferred in the previous entry:
`CPI_YOY` vs `CORE_CPI_YOY_EX7` (r=0.980, alongside the existing ex-3 pair at r=0.991
-- both strong, as expected from core being a subset of the headline basket) and
`OIL_PRICE` vs `OIL_EXPORTS_VOLUME` (r=-0.048, n=88).

The second one is worth a note: it was added specifically to test a hypothesis the
`OIL_PRICE` vs `OIL_EXPORTS_VALUE` pair's own interpretation had raised -- that
value's weak correlation with price (r=-0.170) might be because export value also
moves with shipped volume, independent of price. A near-zero price-vs-volume
correlation is exactly the supporting evidence for that: volume really does appear to
move roughly independently of price in this data, over 2019-2026. Recorded in
`pairs.py` as a cross-reference between the two entries rather than as a coincidence.

Both indicators checked clean against the guardrails before adding (no `lifecycle`
flag, no `cumulation`, not an `international_projection` series) -- no new
`ACKNOWLEDGED_LIFECYCLE`/`FORECAST_CUTOFF_YEAR` entries needed. 8 pairs now, still
under the 10-pair cap `test_pairs_config.py` enforces. 53/53 tests, no code changes --
this was purely `pairs.py` config plus the `analysis/README.md` count update.

## 2026-09-04 — lag scans, and a pattern they actually surfaced

The correlation pass's own report had flagged this as unbuilt: `OIL_PRICE` vs
`EXCHANGE_RATE`'s interpretation said outright "a same-month linear read may
understate a lagged or asymmetric response... a lagged version is a reasonable
next step, not built here." Built it -- as an extension of the existing
mechanism, not a new module: `correlate.lagged_correlation(x, y, lag)` correlates
`x[t]` against `y[t+lag]` (positive lag = x leads y), `lag_scan` runs it across
`-max_lag..+max_lag`, and `Pair` gained an opt-in `max_lag` field. Sign convention
verified empirically before trusting it in the report -- a first attempt at the
verification used a straight linear ramp for x and got r≈1.0 at every single lag,
which proved nothing (a monotonic ramp correlates with any shift of itself);
redone with a non-monotonic fixture and a known y[t]=x[t-2] construction, which
correctly peaks at exactly lag=+2, r=1.0, and nowhere else.

Enabled on the three pairs where a delayed or asymmetric response is
economically plausible: `OIL_PRICE` vs `EXCHANGE_RATE`, vs `OIL_EXPORTS_VALUE`,
vs `OIL_EXPORTS_VOLUME`. The other five (contemporaneous-by-construction pairs
like the two core-inflation ones, or GOV_REVENUE/GOV_EXPENDITURE at n=11 where
a lag scan would shred an already-small sample further) were left at the
default `max_lag=0`.

**What it found**: `OIL_PRICE` vs `OIL_EXPORTS_VALUE` goes from r=-0.170 at
lag 0 to r=0.746 at a 3-month lag (n=85) -- a real, coherent pattern, not
noise-fishing, because the companion pair (`OIL_PRICE` vs
`OIL_EXPORTS_VOLUME`) shows nothing comparable at *any* lag tested (best is
0.124). Read together: price affects recorded export *value* with roughly a
quarter's delay -- plausible given shipping/settlement/invoicing lags on
commodity exports -- while the physical *volume* shipped moves independently
of price at every lag checked. `OIL_PRICE` vs `EXCHANGE_RATE`'s lag scan, by
contrast, found nothing at any shift (strongest is r=-0.168) -- a real
negative result that reinforces the original near-zero contemporaneous
reading rather than hiding a stronger one.

Report output added a per-pair lag table plus a "strongest same-window
reading" callout, worded as descriptive on purpose: scanning several lags and
reporting the best one is itself a multiple-comparisons problem, stated
explicitly in the report's own Methodology section, not just here. 5 new
tests (58/58 total): zero-lag matches the contemporaneous figure, the known
lead-lag construction resolves to the right lag and sign, correlate_pair
wires max_lag through correctly (and leaves it off when unset), and the
report renders the table. No new dependency.

## 2026-09-04 — significance testing, and what it changes about how to read the pairs

Every report in this analysis phase had carried the same disclaimer since the first
one: "No statistical significance testing... a coefficient alone is not proof of a
relationship." Closed that gap with `scipy` (first new dependency this project has
added since `pypdf`) -- `scipy.stats.pearsonr` replaces the separate `pandas.Series
.corr()` call everywhere a correlation is computed, since it returns the identical r
plus a p-value in one call rather than computing r twice through two libraries.

Every pair and every lag-scan point now carries a two-sided p-value (H0: no linear
correlation) and a plain "significant / not significant at 5%" label, computed by
`correlate.pearson_with_p`, which returns `(None, None, n)` below n=2 or for a
constant series -- same "undefined, not zero" treatment already used throughout this
module, not a new exception path.

**What it actually changed about how to read the existing 8 pairs**: not much shifted,
but two things sharpened. `GOV_REVENUE` vs `GOV_EXPENDITURE` (r=0.904, n=11) had been
flagged with "treat as descriptive, not confirmatory" purely because of its small
sample -- the p-value (<0.001) says the relationship is strong enough that even 11
points rule out "no relationship" convincingly; the earlier blanket small-n caveat was
more cautious than the number itself warrants. The opposite lesson showed up in
`REER`/`NEER` vs `CPI`: both read as "significant at 5%" (p=0.007, p<0.001) on
correlations of only -0.197 and -0.245 -- large n (186, 187) makes weak relationships
easy to detect, so "significant" here says nothing about size. Both `analysis/README.md`
and every report's own Methodology section now say this directly, with these two pairs
named as the live example, not a hypothetical one.

The lag scan's "strongest same-window reading" callout now shows its p-value too --
`OIL_PRICE` vs `OIL_EXPORTS_VALUE`'s lag+3 finding (r=0.746) comes in at p<0.001, which
is additional, real evidence for reading it as a genuine pattern rather than one of
seven lags landing high by chance. The report's own methodology text is explicit that
this is still not corrected for running multiple tests (one per pair, one per lag) --
scipy gives p-values, not a multiple-comparisons correction, and none was added.

6 new tests (64/64 total): pearson_with_p matches pandas' r exactly and handles n<2 and
constant-series edge cases without raising (scipy raises below n=2, returns nan+a
ConstantInputWarning for a constant series -- both now handled explicitly rather than
left to propagate), report formatting for p-values and the significance label, and the
new headline line renders correctly. requirements.txt gained `scipy>=1.11`.

## 2026-09-04 — Bonferroni correction, and it actually separates two pairs that looked alike

`analysis/README.md` had named this as the one gap left after significance testing
landed: "No multiple-comparisons correction (Bonferroni or similar) on the
significance tests, even though this report runs several of them." Closed without a
new dependency -- Bonferroni is arithmetic (divide alpha by the number of tests), not
a library call.

`report._count_tests` counts every distinct test a report actually represents: one
per pair's headline correlation, plus one per non-zero lag on the three pairs with a
lag scan -- a scan's own lag-zero point is the same test as that pair's headline, not
counted twice. Today's report: 8 pairs + 3 pairs x 6 non-zero lags = 26 tests, giving
a corrected threshold of 0.05/26 = 0.0019. Each result now states whether it survives
that threshold, but only when the uncorrected 5% test already passed -- a reading
that misses the easy bar trivially misses the stricter one too, so saying so twice
would be noise, not information. (Caught this exact redundancy in the first version
of the test for it, which asserted a Bonferroni clause on a non-significant p-value
and failed against the actual, more sensible behavior -- fixed the test, not the
code, once it was clear which one was right.)

**What it changed**: `REER` vs `CPI` (r=-0.197, p=0.007) reads "significant at 5%"
uncorrected but does *not* survive Bonferroni correction; `NEER` vs `CPI` (r=-0.245,
p<0.001), its near-twin by construction, does. The two had looked like duplicates of
each other from r alone -- the correction is what actually tells them apart. The
`OIL_PRICE` vs `OIL_EXPORTS_VALUE` lag+3 finding (r=0.746, p<0.001) survives too,
real additional confidence that it's a pattern and not one of 26 tests landing low
by chance.

1 new test (65/65 total) plus a fix to one existing one. `analysis/README.md` and
each report's own Methodology section now explain the correction directly, with
REER/NEER named as the live example rather than a hypothetical one.

## 2026-09-04 — seasonal decomposition, the next slice of the analysis phase

Asked for "seasonal decomposition and forecasting" together. Two background research
passes plus a Plan-agent design pass ran first, and both converged on shipping
decomposition alone: a full sweep of all 247 monthly+quarterly indicators' actual
processed CSVs (not assumed) found only **4** indicators genuinely economically-seasonal
with enough dense, gap-free history for STL to mean anything -- `CPI`, `EXPORTS`,
`IMPORTS`, `GDP_NOMINAL`. The "obvious" candidates -- industrial production, retail
trade, construction, tourism -- are all brand-new series with 3-5 data points, onboarded
in just the last few months, unusable despite being exactly what you'd reach for first.
Forecasting is a comparably-sized second design (backtest methodology, model choice,
the WEO-forecast-year guardrail `analysis/README.md` already warned about) -- bundling
both would mean reviewing two independent designs in one pass for no size reason: 4
targets is smaller than the correlation phase's own opening commit (8 pairs, 12 files).

`statsmodels>=0.15` is the first new dependency since `scipy`. Verified installable
before committing to the design (`pip install --dry-run`): a prebuilt wheel exists for
this environment's Python 3.14, no compilation, no conflicts against the existing
numpy/pandas/scipy.

**New shared module, not feature-local**: `scripts/analysis/timeseries.py::prepare_level`
carries the same decumulation/lifecycle/forecast-cutoff guardrails
`correlate.prepare_indicator` already has, but returns the level as-is rather than a
growth-rate transform (STL separates trend/seasonal/residual out of the level itself;
growth-rate-ing first would hand it an already partially-deseasonalized series). Built
shared, not folded into `decompose.py`, specifically so the next slice (forecasting)
reuses it without a third copy-paste -- this is what actually implements the
contamination guard the README already promised, not just names it. One new guardrail
beyond what correlation needed: after decumulation, the series is reindexed onto a
regular calendar grid and refused if that reveals a gap -- all 4 targets are gap-free
today, but the pipeline re-runs daily, and this is what keeps that true going forward.

`scripts/analysis/decompose.py`: STL (`statsmodels.tsa.seasonal.STL`), `robust=True`
fixed for every target (each window contains at least one large transient shock -- 2020
COVID, the 2022 KZT devaluation -- and a non-robust fit would let one anomalous period
distort the seasonal estimate for that calendar position across every year). Reports the
average seasonal effect by calendar month/quarter (12 or 4 rows, not a dump of every
observation), trend direction, and seasonal strength via the standard Hyndman &
Athanasopoulos measure (`max(0, 1 - Var(resid)/Var(seasonal+resid))`, not
`Var(seasonal)/Var(original)` -- the naive version would be dominated by trend for
`GDP_NOMINAL` specifically). A `MIN_CYCLES=3` guardrail (stricter than STL's own ~2-cycle
minimum) refuses a target outright rather than decomposing it with a louder caveat.

**Verified, not assumed** -- ran the real script against the live data before writing
anything about its output: `GDP_NOMINAL` comes back with seasonal strength 0.985, Q4
running far above Q1-Q2 every cycle -- the same Q3-to-Q4 pattern the outlier-check work
found independently weeks ago while fixing `validate_outliers`'s cumulation-awareness,
now confirmed a second way. `IMPORTS` (0.688) shows meaningfully more seasonal structure
than `EXPORTS` (0.204); `CPI` is weakest of the four (0.174) once the 2022 devaluation's
inflation spike is downweighted by `robust=True` rather than read as a permanent
November/December effect. Caught and fixed two real bugs from that live run before
trusting the report: a duplicated "rose, rose" in the trend-direction line, and
unreadable 13-digit `GDP_NOMINAL` figures with 3 decimal places of false precision --
both fixed (thousands separators, 2 decimals uniformly) and reverified.

The STL-recovery test is worth naming: a synthetic 8-year series with a *known*,
deliberately irregular seasonal pattern (not a symmetric sine, which could mask an
off-by-a-few-months alignment bug) recovers every month to within 0.05 of the true value
and seasonal_strength=1.0 -- checked by actually running it during implementation, not
assumed from the formula being "obviously correct."

22 new tests (87/87 total): `test_timeseries.py` (guardrails, including the new gap
check), `test_decompose.py` (the seasonal-recovery test, `_variance_explained` hand-
computed against real arithmetic, guardrail propagation, report rendering),
`test_seasonal_targets_config.py` (mirrors `test_pairs_config.py`, plus a
period-matches-real-frequency check `pairs.py` doesn't need). `transformations.py`'s
`seasonal_adjust_placeholder` got a docstring-only update pointing at where the real
implementation actually lives (`git diff` confirms no behaviour change) -- it stays a
documented no-op rather than a thin pandas-wrapping stub, since `transformations.py` is
deliberately pandas-free and STL genuinely needs a date-indexed `pandas.Series` plus
`statsmodels` itself.

Deliberately out of scope: forecasting (the named next slice -- `timeseries.py` is
already built for it to reuse), any indicator beyond the 4 verified targets, charting
(the calendar table is useful without one), CI wiring, `project_knowledge/`/Claude
Project sync (same open decision the correlation phase already deferred).

## 2026-09-04 — forecasting, closing out the "seasonal decomposition and forecasting" request

The deferred second half of the request decomposition shipped alone above. Same 4
curated targets (`CPI`, `EXPORTS`, `IMPORTS`, `GDP_NOMINAL`), independently
re-justified in a new `scripts/analysis/forecast_targets.py` against this pass's own
guardrail rather than inherited from `seasonal_targets.py` -- the same "a different
pass's decisions aren't inherited" split every override dict in this codebase already
keeps. `scripts/analysis/timeseries.py::prepare_level` is reused exactly as built
(`git diff` confirms zero changes to it, `transformations.py`, `requirements.txt`, or
`test_timeseries.py`) -- this is the payoff of building it shared during the
decomposition slice instead of folding it into `decompose.py`.

**Model choice, verified before committing to it**:
`statsmodels.tsa.exponential_smoothing.ets.ETSModel`, fixed spec ETS(A,A,A) --
additive error, additive trend, additive seasonal -- not the classic
`statsmodels.tsa.holtwinters.ExponentialSmoothing`. Ran both during planning: the
classic implementation's fitted result has no `get_prediction()`, only `.simulate()`
(manual quantile-taking needed for an interval, and a bare int as `rng=` throws a live
`FutureWarning` on the installed statsmodels 0.15.0). `ETSModel.fit(disp=False)` gives
`get_prediction(...).summary_frame(alpha=0.05)` with clean `mean`/`pi_lower`/`pi_upper`
columns, closed-form for this additive spec. **Two fits per target**: a *backtest* fit
trained on all but the last `horizon` observations, scored (MAE/RMSE/MAPE) against the
real, already-known holdout actuals; a separate *forward* fit trained on the full
series, forecasting `horizon` periods beyond the last real observation with a 95%
interval -- labeled UNVERIFIED in the report, since no held-out actual exists for those
periods by construction. `horizon` is 12 for monthly targets, 4 for quarterly
(`PERIOD_TO_HORIZON`, a one-year-ahead framing for both). `MIN_CYCLES=3` gates the
post-holdout training length this time, not the full series -- independently
redeclared in `forecast.py`, not imported from `decompose.py`, same reasoning as
always: it gates a different quantity here.

**A real bug found during planning, not assumed away**: the level `prepare_level`
returns has no `.index.freq` set, so `ETSModel` warned on every single fit ("No
frequency information was provided..."). Verified independently before accepting the
fix, not just trusting the planning pass's claim: `warnings.simplefilter("error")`
around the fit (any warning would raise) fired zero warnings after adding
`s = s.asfreq(timeseries.FREQUENCY_OFFSET[meta["frequency"]])` right after
`prepare_level` returns, with identical values and length confirmed before/after.
Reuses the shared `FREQUENCY_OFFSET` constant directly -- it has to be the exact grid
`prepare_level`'s own gap-check already validated, not a second value that could drift
from it. **A second bug found while reading the live-generated report, not by any
test**: the training-window line read "Training window: 2011-01-01 .. 175
observations." -- a count sitting where an end-date belongs, inconsistent with the
adjacent Holdout line's `start .. end (count)` format. Fixed by adding `train_start`/
`train_end` fields to `BacktestMetrics`, populated from the training split's own index,
and reverified the fix changed only the rendering, not the underlying numbers (MAPEs
identical before/after to 2 decimals).

**Verified, not assumed** -- ran the real script against the live data before writing
anything about its output: CPI backtest MAE=0.27 RMSE=0.36 MAPE=0.27% (n=187,
train=175, the deepest training-length margin of the four at 4.86x); EXPORTS
MAE=735,042.76 RMSE=1,046,230.93 MAPE=10.54% (n=90, train=78, tightest margin at
2.17x, and per the decomposition pass also the least seasonal structure of the four --
seasonal strength 0.204); IMPORTS MAE=464,109.00 RMSE=583,477.33 MAPE=8.10% (same
construction and margin as EXPORTS); GDP_NOMINAL MAE=1,656,615,106,823.13
RMSE=2,038,155,631,710.74 MAPE=3.57% (n=66, train=62, 5.17x margin, despite forecasting
raw 13-digit KZT figures). No pass/fail threshold on any of these -- every MAPE is
reported as-is, EXPORTS' double-digit figure included, matching this project's
"report the number, don't hide it" pattern throughout.

The synthetic-recovery test is worth naming, same spirit as `decompose.py`'s: an
8-year, zero-noise series with a known, deliberately irregular (non-sinusoidal)
seasonal pattern and a linear trend recovers a near-exact backtest (MAE/RMSE both
~0 to 4 decimal places) -- `ConvergenceWarning` suppressed only inside this one test
(a fully deterministic series is a known statsmodels MLE edge case, verified none of
the 4 real targets ever trigger it, so production code leaves it unsuppressed).

19 new tests (106/106 total): `test_forecast.py` (MAE/RMSE/MAPE hand-computed against
`actual=[10,20,30]`/`forecast=[12,18,33]`, the synthetic-recovery test, all 4
guardrails -- below-minimum training length, period-vs-frequency mismatch,
horizon-vs-period mismatch, unwrapped `timeseries.SeriesGuardrailError` propagation --
and report-rendering assertions including the UNVERIFIED label and the corrected
training-window date-range format), `test_forecast_targets_config.py` (mirrors
`test_seasonal_targets_config.py`, plus a horizon-matches-`PERIOD_TO_HORIZON` check and
a test that loads the real unified dataset and statically re-verifies each target's
post-holdout training length still clears `forecast.MIN_CYCLES * period` -- the same
quantity the runtime guardrail checks, caught here if a target's history ever shrinks).

Deliberately out of scope: `STLForecast`/`SARIMAX` as alternative models (verified
working during planning, not built -- a second hyperparameter set for no clear v1
benefit), automatic model-order selection, damped trend, multiplicative
seasonality/error, any target beyond the 4, CI wiring,
`project_knowledge/`/Claude Project sync (same deferred decision as decomposition),
multi-step-ahead accuracy decay (one MAE/RMSE/MAPE per target across the whole
holdout, not broken out by how many periods ahead -- a real, named, unanswered
follow-up question).

## 2026-09-04 — charting, visualizing both analysis passes' output

Asked what's next after forecasting shipped; recommended charting since both passes'
own docs already named it as a natural follow-on "once this output's shape has been
reviewed" -- it had been reviewed twice by then. Scope confirmed before starting:
decomposition + forecasting only, not the correlation pass's lag scans. Went through
Plan Mode again -- an Explore agent read the 4 decomposition-side files in full, a
Plan agent designed and partially verified the approach against live data (both
read-only), and I independently re-read the report/CLI files myself and re-verified
every cited line number before writing the plan.

**Zero changes needed to `decompose.py`** -- `seasonal_by_period` (the 12/4-row
table the report already renders) was already everything a seasonal-effect bar chart
needs. Confirmed live before committing to this: re-running `decompose.run_all()`
reproduced the exact already-shipped seasonal strengths (CPI 0.174, EXPORTS 0.204,
IMPORTS 0.688, GDP_NOMINAL 0.985). `forecast.py` needed two small, free additions --
a new `HistoryPoint(date, value)` dataclass, a `history` field on `ForecastResult`,
and a `predictions` field on `BacktestMetrics` -- retaining two values
(`s`, the prepared series, and `backtest_forecast`) that `forecast_target()` already
computed and previously discarded once reduced to MAE/RMSE/MAPE. Not new modeling
work: a forecast chart with no historical context can't show whether a forecast
looks plausible relative to where the series came from, and the backtest's own
predicted values are the visual form of what "backtest" means. Verified live during
planning: capturing `s` and `backtest_forecast` for CPI reproduced the exact
already-shipped backtest MAE (0.2748380824808585) from the captured values
themselves, and grep confirmed only 2 real construction sites exist for
`BacktestMetrics(`/`ForecastResult(` in the whole repo (`forecast.py` and
`tests/test_forecast.py`'s `_sample_result()`) -- the "adding a required dataclass
field breaks an existing fixture" gotcha that has hit this project a few times now
had a fully known, small blast radius here.

`matplotlib>=3.11`/`pillow>=12.3` are the new dependencies. Verified installable via
dry-run during planning, then actually installed for real and smoke-tested headless
(`matplotlib.use("Agg")`, real `savefig`, real `PIL.Image` open, real
`plt.close(fig)`/`get_fignums()` check) before writing any chart-rendering code --
zero warnings under `warnings.simplefilter("error")`. New shared
`scripts/analysis/charts.py` (mirrors `timeseries.py`'s shared-plumbing role):
`chart_filename()` (pure naming, importable by the zero-I/O report modules without
pulling in matplotlib.pyplot), `add_disclaimer()` (a small "DERIVED, NOT SOURCED"
caption stamped into every chart image itself -- a PNG can be shared standalone,
disconnected from its report's surrounding disclaimer text, and this project has
been strict everywhere else about that exact risk), `save_figure()` (stamps the
disclaimer, saves, and closes the figure -- matplotlib leaks every created figure
until `plt.close()` runs). Two new feature-local chart-builder modules,
`seasonal_charts.py`/`forecast_charts.py`, each a thin `render_target_chart()` +
`render_all()` pair, called from `decompose_seasonality.py`/`forecast_series.py`
before the report string is built (so the markdown image link's target already
exists by the time it's referenced). `seasonal_report.py`/`forecast_report.py`
stayed genuinely zero-I/O -- they only import `charts.chart_filename`, never
`charts.save_figure`.

**Verified, not assumed** -- ran both real scripts end to end after wiring: identical
MAPE/seasonal-strength numbers as before (confirms the new fields changed nothing
about the underlying computation, only what's retained), 8 real PNGs written,
~394KB total (seasonal charts ~21-27KB each, forecast charts ~67-75KB each at
DPI=120). Opened the real generated CPI and GDP_NOMINAL charts from both passes
before trusting them -- same "read the live output before committing" discipline
that caught 2 real bugs in the decomposition/forecasting report text earlier this
session. All four looked right: CPI's seasonal bar chart shows the winter-high/
summer-low pattern the report text already described; CPI's forecast chart clearly
shows the 2015-16 and 2022 devaluation spikes, a backtest line tracking the actual
closely, and a widening 95% band in the UNVERIFIED region; GDP_NOMINAL's forecast
chart rendered its 13-digit KZT scale as a clean `1e13` axis offset with no extra
formatting code needed, and its sharp annual Q4 spikes (matching the 0.985 seasonal
strength already reported) are visually obvious in both the actual and backtest
lines.

7 new tests (113/113 total): `test_charts.py` (naming convention,
`save_figure`/`add_disclaimer` against real rendered figures, a subprocess-based
check that importing `charts` alone never pulls in `matplotlib.pyplot`), one new
chart-render test each in `test_decompose.py`/`test_forecast.py` (real synthetic
data through the real mechanism, rendered, checked as a valid non-trivial-size PNG
via Pillow), plus `test_forecast.py`'s `_sample_result()` fixture and its
deterministic-recovery test extended for the two new required fields. `git diff
scripts/analysis/decompose.py` confirmed empty, matching the zero-change claim.

Deliberately out of scope: interactive/HTML charts (matplotlib static PNGs match
this project's markdown-report-centric output model); unit-aware y-axis labels
(`config/indicators.yaml` does carry a `unit` field, but matplotlib's default axis
formatting was already sufficient in every real chart checked, including
GDP_NOMINAL's 13-digit scale); a chart retention/cleanup policy (would contradict
the deliberate never-deleted convention the `.md` reports already use, and isn't
worth building before there's a real reason to).

## 2026-09-04 — lag-scan charts, closing out the charting slice's one deferral

Asked to continue after the decomposition/forecasting charting slice shipped.
That slice had explicitly deferred the correlation pass's lag scans as a
"different, smaller-population output shape" -- re-read `pairs.py`, `correlate.py`,
`report.py`, and `analyze_correlations.py` in full before touching anything (not
relied on memory from earlier this session) to confirm the real current field
names and structure rather than risk a stale assumption.

**Zero changes needed to `correlate.py`** -- `PairResult.lag_profile` (a list of
`LagPoint(lag, r, p, n)`) already carried everything a lag-scan chart needs, the
same zero-change situation `decompose.py` was in for the first charting slice, and
unlike `forecast.py`'s two required field additions there was no discarded
intermediate value to retain here at all. New `scripts/analysis/lag_charts.py`
reuses the shared `charts.py` module exactly as-is (`chart_filename`,
`save_figure`, `add_disclaimer` -- none of it needed touching for a third pass),
following the established bar-chart visual language from the seasonal-effect
chart (discrete x positions, zero line, sign-colored bars) rather than the
forecast pass's line-chart style, since a lag scan is a small number of discrete
shifts (7 points, -3..+3 for all 3 scanned pairs today), not a continuous time
series. Only pairs with `max_lag > 0` (3 of 8: `OIL_PRICE` vs `EXCHANGE_RATE`, vs
`OIL_EXPORTS_VALUE`, vs `OIL_EXPORTS_VOLUME`) get a chart -- `render_all` filters
this, and `report.py`'s `_chart_embed` is only called inside the same
`if result.lag_profile:` guard that already gates the existing lag table.
`report.py` stayed genuinely zero-I/O (only imports `charts.chart_filename`,
never `charts.save_figure`), matching `seasonal_report.py`/`forecast_report.py`'s
precedent exactly. `_pair_section` gained a `run_date` parameter threaded down
from `build_report`, which every existing test already passes as a keyword
argument -- confirmed zero existing tests call `_pair_section` directly, so this
signature change broke nothing.

A small defensive branch worth naming: a `LagPoint` can have `r=None` (fewer than
2 paired observations after the shift, or a constant series) -- `render_pair_chart`
filters those out of the bars entirely (never plots a misleading 0-height bar for
"undefined") and annotates the count of skipped lags directly on the chart. None
of the 3 real scanned pairs hits this in practice (verified via the real run
below), so it's covered by a dedicated test with a directly-constructed
`PairResult`, not real data.

**Verified, not assumed** -- ran the real script after wiring: identical r values
as before (0.063/-0.170/-0.048 for the three lag-scanned pairs' contemporaneous
readings, confirming the change touched nothing about the computation), exactly 3
charts written (matching the 3 pairs with `max_lag > 0`), ~83KB total (~26-31KB
each). Opened the real `OIL_PRICE` vs `OIL_EXPORTS_VALUE` chart before trusting
it: it visually reproduces the exact pattern this project's own `analysis/
README.md` already described in words from the original lag-scan work --
near-zero/negative bars around lag 0, rising to r≈0.75 at lag +3 -- same
"read the live output before committing" discipline used throughout this session.

5 new tests (118/118 total), all in `test_correlate.py` (no new test file, matching
how the first charting slice extended `test_decompose.py`/`test_forecast.py`
in place rather than adding parallel chart-only files): `render_pair_chart`
returns `None` for a pair with no lag scan; writes a real, valid PNG for a real
`correlate_pair()` result; skips undefined lag points without crashing or
mis-plotting them; `render_all` returns paths only for the pairs that actually
got a chart; the report embeds the chart image link only for a pair with a lag
scan, never for one without. `git diff scripts/analysis/correlate.py
scripts/analysis/pairs.py` confirmed empty, matching the zero-change claim.

Deliberately out of scope: everything the first charting slice already scoped out
(interactive/HTML charts, unit-aware y-axis labels, a chart retention/cleanup
policy) applies here too, unchanged.

## 2026-09-14 — model sync, phase 0: a contract between the Excel GDP model and the unified dataset

The analyst's Excel GDP model (`1_Model_GDP_p_a_2025_…_rev_2026-09-14.xlsx`, kept
on Yandex.Disk, not in this repo) had just been brought to BNS facts for 2024-2025
by hand, from 40 BNS dynamic tables plus World Bank, IMF and NBK series. Comparing
what the model needs with what this pipeline already publishes showed 29 indicator
groups: 5 fully covered, 11 only as national totals, 13 absent (everything by
section or by region, natural volumes, World Bank prices, exports by commodity).
This entry is the first of six planned phases: make the part that already matches
flow from the pipeline, and make any later disagreement visible.

**What was added.** `config/model_map.yaml` — one entry per pipeline variable (21
entries, 22 cell targets) naming the workbook cells that should carry its annual
value, the annualisation rule (`last`, `mean`, `december`, `sum`), the unit scale
(the pipeline stores tenge, the model млн ₸) and a tolerance. `scripts/model_sync.py`
reads the workbook twice (formulas and cached values), annualises the unified series
and prints one line per cell and year. The one design rule worth stating: a cell that
holds a formula is a CONTROL — compared, never written, because the model computes it
— and only a cell that holds a number is an INPUT that `--apply` may rewrite. So the
loader can never replace the model's own logic with a pasted value. `--apply` writes
through a private Excel instance (`scripts/lib/excel_apply.ps1`, the same applier used
for the manual update: full recalculation, save-as to `--out`, never in place), puts a
comment on each written cell naming the variable, source and previous value, and
appends the change to the model's own «Журнал_правок» sheet. This step is a local,
Windows-only tool and is deliberately not wired into `update_all.py`.

**Verified, not assumed.** The first real run against the model: 111 checks, 107
already equal, 0 control mismatches, 0 missing, 4 input differences — and all four
were real stale cells, not loader noise: employed persons and the average wage for
2023 on the «Прогнозы ЦГО» sheet still held the old ЦГО estimates (8 930.5 thousand
vs BNS 9 081.92; 349 748 vs 364 295 tenge), and the 2023-2024 annual exchange rate
came from a different averaging than 2025 (456.31/469.21 vs the daily mean
456.79/469.02; 2025 already was the daily mean). Applied through `--apply`: the
model's «Контроль» sheet (GDP, GVA, deflators, 20 sections, 2023-2030) did not change
by a single cell, which confirms the fact-year deflators no longer depend on those
rate cells; the re-run reports 111/111 equal. Two findings recorded in the map's
comments rather than mapped: `SUBSIDIES` is not subsidies on products (980.7 bn ₸ in
2023 against BNS's 339.6 bn; `TAXES_ON_PRODUCTS` does match), and the quarterly
`GDP_NOMINAL` is cumulative within the year, so the annual `GDP_INCOME_METHOD` is the
series to use for nominal GDP.

9 new tests in `tests/test_model_sync.py` (127/127 total): the four annualisation
rules only ever see observations dated inside the requested year and return `None`
rather than a fabricated value for an absent one; an unknown rule is an error, not a
default; scale-then-offset; year-header parsing ignores strings and booleans; a
formula cell can never reach the `diff` status; `build_ops` writes only `diff`
inputs and journals each; and `model_map.yaml` names only variables that exist in
`indicators.yaml`.

Deliberately out of scope, for the later phases: an item dimension (section / region)
in the unified data, which is what 24 of the 29 indicator groups need; new BNS
fetchers for the 40 tables; World Bank and EIA as agencies; exports by commodity from
the trade file already downloaded; a `manual_inputs.yaml` for forecasts that are
assumptions, not facts.

## 2026-09-14 — model sync, phase 1: national accounts by section, component and ownership form

The model's core is a breakdown — GVA by ОКЭД section, by industry division, GDP by
expenditure component, income components by section, the non-observed economy, GVA
by form of ownership — and `macro_long.csv` cannot hold one, because its contract is
one value per (date, variable). So this phase adds a parallel item-level layer with
the same rules rather than bending the existing one: `config/dims.yaml` (16 datasets
from 13 BNS dynamic tables), `scripts/fetchers/bns_dims.py`, `scripts/lib/dims.py`,
`scripts/update_dims.py`, `data/processed/dims/<id>.csv`, `metadata/bns/<id>.json`,
revisions keyed on (date, item), and `data/unified/macro_dims_long.csv` (`macro_long`'s
columns plus `item_code`, `item_name`; 5 682 rows on the first run). `update_all.py`
runs it after the agency updaters and rebuilds the dims file with the rest.

**Why the xlsx export, not the JSON cube.** Every table's JSON cube was downloaded and
inspected first, the way the existing BNS fetchers read theirs. It is not the same
data: 4439 and 4435–4437 carry only regional/national totals there (no sections, no
components), 4453 stops at 2024 while the xlsx has 2025, and 4446/4448 return 404.
The xlsx export is the file the Excel model was hand-loaded from on 2026-09-14, which
also made it possible to test the parsers against ~2 000 already-verified cells (below).
Three sheet layouts cover everything (`periods_across`, `region_blocks`,
`year_subcolumns`); parsers find header rows by content, take only the "YYYY год"
columns (quarterly columns are year-to-date), date annual values 31 December like the
other annual BNS series, and resolve every data label through a dictionary
(`dictionaries/okved_sections.csv`, `dictionaries/expenditure_items.csv`). A label that
matches no entry — the event that must not pass silently when BNS renames or adds a
line — raises `StructuralChangeError` with the unmatched labels listed.

**Three parser defects the first live run caught, all mine.** BNS writes
«Косвенно-измеряемые услуги» with a hyphen (dictionary regex fixed to accept both);
the income tables label quarters "1 квартал 2025 года", which *contains* "2025 год",
so an unanchored year search took Q1 for the annual value — the compensation total
for 2025 came out as 8.8 trn instead of 49.4 trn (regex now anchored at the start of
the cell); and the expenditure volume index publishes no index for net exports,
inventories or valuables (11 items, not 15 — the minimum-items guard was set from the
nominal table). After the fixes: 16/16 datasets ok, 153/153 tests.

**Verified, not assumed** — `model_map.yaml` gained 17 item-level mappings (the model's
own «Факт_БНС» input sheet read through its code column, plus the section totals,
the МКИ sheet, the income sheet with one column block per component, the NOE sheet,
and the ownership sheet over 2010–2025) and `model_sync.py` learned `dims_variable`
entries, explicit `year_columns` for text-headed sheets, and `item_column` scanning.
Against the model as it stands: 2 077 checks, 2 019 equal, 0 input differences,
0 control mismatches, 58 "missing" — all of them ownership cells that BNS leaves
empty (the phenomenon is absent) and the model holds as 0; the loader reports the
absence rather than inventing a zero. Two contract corrections came out of the run and
are recorded as comments in the map: BNS's «Итого по отраслям» in table 4452 includes
the net-taxes row, so it equals the model's income-method GDP (row 30), not the sum of
sections (row 27); and the model's aggregate volume indices are chained in fixed 2023
prices, which sits 0.2 p.p. from BNS's previous-year-price aggregate in 2025 — a known
property, so that control's tolerance is 0.25 rather than 0.15.

27 new tests (153 total): the three parsers on synthetic grids replicating the live
layouts, the structural-change path on an unknown label, dictionary uniqueness and
every canonical name resolving only to its own code, label variants actually seen in
BNS files (hyphenated, unspaced, footnoted), duplicate (date, item) rejection,
item-keyed revisions, the dims long format extending the scalar one, and the
`model_sync` extensions (code-column scanning with aliases, dims loading).

Deliberately out of scope: the regional dimension (phase 2 — the `region` column
exists in both long files but only ever holds `national`); `DATA_CATALOG.md`, which
is generated from `indicators.yaml` and does not yet list the item-level datasets;
quarterly year-to-date values from these tables (skipped, not stored); and the
outlier warnings on small NOE shares, which are warnings by design.

## 2026-09-14 — model sync, phase 2: the regional dimension

The model's production block is 20 section headings each followed by 21 region rows
(the 20 regions of 2022 plus the closed Южно-Казахстанская), and its «Факторы» sheet
carries population, labour force, employment and unemployment by region. Until now
`region` in both unified files only ever held `national`. This phase fills it.

**What was added.** `dictionaries/regions.csv` — 22 codes with one regex each, matched
on a normalised label that folds the spellings BNS actually uses across its tables:
«Акмолинская», «Акмолинская область», «АКМОЛИНСКАЯ ОБЛАСТЬ», «Область Абай3)»,
«З-Казахстанская», «Жетісу»/«Жетысу», «Ұлытау», «г.Алматы»/«г. Алматы»/«Г.АЛМАТЫ»,
with Kazakh letters mapped to Russian shapes, footnote digits dropped and district
rows («Абайский район», «Кокшетау г.а.») matching nothing. `lib/dims.py` gained the
`region` column throughout (processed, revisions keyed on (date, region, item),
unified). `fetchers/bns_dims.py` gained a fourth layout (`group_blocks`, for the
population table's «Все население / Городское / Сельское» blocks with their sex
sub-blocks), region rows for `periods_across` and `year_subcolumns`, all-regions
mode for `region_blocks`, per-dataset `label_overrides`, and `strict: false` for
sheets that also list districts. 17 new datasets in `config/dims.yaml` (34 in all,
24 589 unified rows, 22 regions): ВРП and GVA by section and region (5927), the
regional GVA volume indices (450904) and the ВРП volume index (5926), average
population by region × settlement type × sex (6576), the labour market by region
(102790–102800: labour force, employed, unemployed, employees, self-employed,
unemployment rate), employment by BNS group by region (443430/435/438), employment
by section (5831), and fixed capital investment by region and by section with its
volume indices (5546/5547/5549). `model_map.yaml` gained 21 regional mappings and a
`blocks` form (item -> row range of region rows, names resolved from the sheet);
`model_sync.py` treats an EMPTY input cell as fillable — it was reported as "missing"
before, which hid the 80 empty regional cells of 2024–2025.

**Parser defects the live run caught, all mine again.** BNS wraps column headers
mid-word with a hyphen («Горнодобы-вающая», «промышлен-ность» in 450904), so a
hyphen between two letters is now dropped in normalisation and the dictionary
regexes accept an optional hyphen; the 2010–2018 sheet of 5927 names the ВРП column
«Всего» and carries КИУФП (FISIM) — dataset-level overrides; period rows in 450904
carry footnotes («20211)»), so that dataset's year regex allows one; and the
investment-by-section table has no «%» column for 2003, which the sub-column parser
now detects instead of reading 2004's value as 2003's index.

**Verified, not assumed** — 184/184 tests (14 new: region labels seen in BNS files and
in the model, the group-blocks parser, region rows in both row-wise layouts, the
missing-sub-column case, hyphenated and Latin-lettered labels, region-keyed
revisions). Against the model: 5 143 checks, 4 753 already equal, 105 differences on
input cells, 116 control mismatches, 169 "missing". The 105 were applied through
`--apply` (the model's «Контроль» sheet did not change by a cell): 22 are BNS's
current 2023 regional population — small revisions plus a reclassification of
51 837 people in Алматинская from urban to rural; 41 are the regional unemployment
rate, empty for 2024–2025 in the model, plus Восточно-Казахстанская 2023, which held
the national 4.6 instead of BNS's 3.4; 40 are regional self-employment 2024–2025,
also empty; and 2 are mining volume indices for Astana and Almaty 2023 where BNS
publishes 0 and the model had nothing. Re-run: 4 858 equal, 0 differences. The 169
"missing" are the closed Южно-Казахстанская rows (63 + 33 + 15) and the BNS-empty
ownership cells already known; nothing was invented for them. The 116 control
mismatches are two findings for the model's author, not the loader's: regional
employment and unemployment for 2024–2025 are formulas in the model (labour force
minus an estimated unemployment) and sit up to ±0.2 % from BNS's published regional
figures; and employment by section is derived in the model from the BNS group totals,
while BNS publishes it directly (5831) — differences reach 29 thousand in section S.

Deliberately out of scope: replacing those formulas with facts (the loader never
overwrites a formula; the author decides); the 2010–2017 sheet of 450904 and the
2013–2018 sheet of 5931, parsed but not mapped to the model; forestry and fishing
volume indices by region (458550/458663 — the model has no rows for them);
`DATA_CATALOG.md` still lists scalar indicators only.

## 2026-09-14 — model sync: the author's two employment decisions, as a contract flag

The model's author decided that regional employment and unemployment for 2024–2025
and employment by section are facts, not model logic. Rather than a one-off script,
`model_map.yaml` gained a per-mapping `replace_formulas: true`, and `model_sync.py` a
matching `Check.replace_formula`: with the flag, a formula cell that disagrees with the
pipeline is reported as `diff` and `--apply` may overwrite it; without it the default
holds — formulas are only ever compared. The decision is therefore visible in the
contract, next to the mapping it applies to, with a comment saying who decided and when,
and every replaced cell carries a comment and a journal row saying the formula was
replaced by a fact.

Applied: 116 cells — regional employed and unemployed 2024–2025 (the model had
estimated unemployment as labour force × the NATIONAL rate and employment as the
remainder), and employment by section 2023–2025 from BNS 5831 (the model had derived
sections from group totals; the sums over sections stay formulas, and the industry
subtotal now agrees with 5831 to the unit). «Контроль» unchanged; the only sheet that
reads these cells is labour productivity, which now rests on published figures.
Re-run of those mappings: 183 equal, 0 differences, 0 control mismatches.

## 2026-09-14 — model sync, phase 3: physical output, production indices, grain

**What was added.** Six datasets (40 in all, 39 387 unified rows): industrial output in
physical units by product and region (5814 — the model's physical-output rows under the
industry nodes are labelled exactly as this table labels its products, so
`dictionaries/products.csv` is that list: coal, oil, gas, ores and concentrates,
foods, beverages, textiles, fuels, electricity, heat, water); the industrial production
index by activity (5792, 53 rows — `dictionaries/industry_divisions.csv`, ОКЭД
divisions and groups); the agriculture volume index by ОКЭД activity (8150, codes from
the sheet); and grain harvest, sown area and yield by region (8160/8154/8166). Parser
additions: `product_blocks` (product label row, then the country and producing
regions), `group_blocks` generalised to labels in column A and to skipping crop groups
the dictionary does not name, a `code_col` for tables that carry their own codes, and
legacy `.xls` reading through xlrd — five of these tables are OLE2 files, not zip-based
xlsx, and the first live run failed on all five with "File is not a zip file" until the
format was detected from the file signature rather than the download name.

**Verified, not assumed.** Seven new mappings: the physical-output rows of the ВДС
sheet (31 products), the oil and gas fact rows of «Прогнозы ЦГО», table 2 of «Факт_БНС»
(the raw BNS index behind every lowest-row ИФО of sections A, B, C, read through the
sheet's code column with the model's own numbering for non-ferrous metallurgy and
casting aliased to ОКЭД 24.4/24.5), and the grain harvest row with its 21 region rows.
First run: 168 equal — every 2023 physical value and all 72 raw indices in table 2
matched to the last decimal, which is the strongest test the parsers could get — 57
differences, 0 control mismatches, 9 missing. Applied: 55 empty 2024–2025 physical-
output cells filled, and the 2023 oil and gas fact rows on the ЦГО sheet refined from
the ministry's rounded 89.9 / 59.1 to BNS's 89.977 млн т / 59.458 млрд м³. «Контроль»
unchanged. Re-run: 225 equal, 0 differences. The 9 missing are BNS-confidential or
absent cells (bauxite 2024–2025, asbestos 2025, grain in regions that grow none) —
nothing invented.

Deliberately out of scope: the coal and electricity fact rows of «Прогнозы ЦГО», which
follow the ministries' definitions (2023: 112 vs BNS 116.4 млн т; 112.8 vs 113.6 млрд
кВт·ч) and need a stated conversion rule before they can be mapped; oil production by
field (ministry data, not BNS); crop-level sown area from 466568; the regional
detail of 5814 (loaded, 22 regions, but the model has national rows only).

## 2026-09-15 — model sync, phase 4: world prices from the World Bank and the EIA (two new agencies)

**What.** The GDP model's world-price block («Внешние и внутренние факторы»: 46 annual
commodity prices in rows 65–124, 16 price indices in rows 146–161, the World Bank and EIA
Brent forecasts in rows 5 and 4) was the last fact block still hand-loaded. It now comes
from two new pipeline agencies:

- `wb` — World Bank Commodity Markets. Four item-level datasets in `config/dims.yaml`:
  `WB_COMMODITY_PRICES_ANNUAL` (69 Pink Sheet series, 1960–2025, 4 099 rows),
  `WB_COMMODITY_INDICES_ANNUAL` (16 indices 2010=100, 1 056 rows),
  `WB_COMMODITY_PRICE_FORECASTS` and `WB_COMMODITY_INDEX_FORECASTS` (the CMO forecast
  table's `2026f`/`2027f` columns only: 92 and 32 rows, April 2026 vintage). Plus one scalar
  series beside the IMF's APSP: `OIL_PRICE_BRENT`, monthly Brent from the Pink Sheet
  (800 points, 1960-01 – 2026-08, `scripts/update_wb.py`).
- `eia` — U.S. Short-Term Energy Outlook. `EIA_STEO_PRICES`: Brent and WTI spot, monthly
  history and forecast from `STEO_m.xlsx` (144 rows, 2022-01 – 2027-12; September 2026
  release, last historical month 2026-08; months after it carry `transformation: forecast`).

**How the files are reached — verified, not remembered.** The CMO page links its files on
thedocs.worldbank.org and the document id in the path changes every release: the link the
model had been loaded from (…-0350012021) is the January 2025 vintage and ends in 2024;
the current one (…-0050012026, "Updated on September 02, 2026") ends in 2025. So
`scripts/fetchers/wb.py` reads the page at run time (plain GET, 200, 56 KB) and takes the
links from it, with the last confirmed link as the fallback and the manifest saying which
was used. The forecast table is linked as a PDF; the xlsx sits at the same path (checked
for April 2026). EIA's `xls/2tab.xlsx` and `STEO_a.xlsx` answer 404; the whole monthly
workbook `xls/STEO_m.xlsx` is what exists and is read (sheets `Dates`, `2tab`).

**Codes.** Neither World Bank file carries a mnemonic row any more, so
`dictionaries/wb_commodities.csv` (69, with `name_en` and `unit`) and
`wb_commodity_indices.csv` (16) define the codes, modelled on the Pink Sheet mnemonics,
with one regex per series matching the labels of both the history file and the forecast
table ("Logs, Cameroon" / "Logs, Africa", "Urea" / "Urea, E. Europe", "Non-energy **" /
"Non-Energy"). English labels get their own normaliser (`dims.normalise_label_en`) —
the Russian one folds Latin letters into Cyrillic. The price sheets' units row is
checked against the dictionary (a changed unit stops the dataset); the sub-group rows
of the forecast table are indented into column B/C, which the first run caught as
"8 items instead of 46" and the parser now handles.

**Plumbing.** `update_dims.py` dispatches the fetcher by each dataset's agency
(`AGENCY_FETCHERS`), takes `--only <agency|id>…`, writes a record-level
`transformation`, and sets `country`/`geography` per dataset (`WLD`, "World (benchmark
prices)"; `region` is `world`). `model_sync.py` gained `rel_tolerance` — the wider of the
absolute and relative tolerances applies, because the price rows span $0.34/kg to
$34 000/t and the World Bank publishes rounded values. `lib/unified.py` takes the scalar
`country` from indicators.yaml (KZ unless said otherwise). `update_all.py` runs
`update_wb` before `update_dims`. Tests: 207 → 290 (`tests/test_wb_eia.py`, a relative-
tolerance case, the dataset-registry test now per agency).

**Model run** (`model_map.yaml` +7 mappings: `wb_prices_history`, `wb_price_forecasts`,
`wb_indices_history`, `wb_index_forecasts`, `brent_reference_control`, `brent_wb_forecast`,
`brent_eia_forecast`): 317 checks — 310 ok, 2 diff, 0 control, 5 missing. Applied 2 cells:
US natural gas 2023 (2.50 → 2.54, revised by the World Bank) and the EIA Brent 2026
forecast (91, the overview table's rounded figure, → 90.8575, the mean of the twelve
monthly values). The five "missing" are Barley 2023–2025 and Shrimp 2024–2025, which
the World Bank no longer publishes as history (`..`) — the model's own numbers there
stay, nothing was invented. Re-check: 312 ok, 0 diff. The 2026 column of «Контроль»
moved by 0.003 % (consensus Brent 79.571 → 79.551 through row 3's average) — the model's
designed propagation of a forecast input, unlike the fact-year loads of phases 1–3 which
left «Контроль» untouched. Journal 1 315 → 1 318 rows. Copy on Yandex.Disk replaced
under a hash check (eee49fc8 → dceb4f43); the original file is unchanged (3f5a1228).

**Found by the way — decisions left to the author, not applied.** An informational scan
of 1991–2025 (2 205 cells: 2 114 ok, 76 diff, 15 missing) shows:
1. Row 66 «сырая нефть марки Брент» holds the World Bank *average* crude (Brent/Dubai/WTI)
   for 1991–2020 — every year within 0.3 % of `CRUDE_PETRO`, 2.5–6.2 % below Brent in
   2011–2020 — and Brent only from 2021 (the phase-3-era load). Row 2 links to it. Whether
   the history should become Brent (`--only wb_prices_history` with `years` widened) is
   the author's call; it would move the historical oil deflators.
2. Rubber TSR20 1999–2016 (5–16 %) and Urea 1991–2020 differ from the current Pink Sheet:
   older vintages of series the World Bank has since redefined (the `**` marker).
3. Grains index 2022: model 105.4, World Bank 150.4 — looks like a slip, not a vintage.

**Not done.** The page-scraping step has only been exercised from this machine, not from
GitHub Actions (the fallback link covers a blocked page, but a stale fallback would go
unnoticed until the October 2 CMO — the log warning is the signal). `OIL_PRICE` (IMF
APSP) and the CTOT indices still carry `country: KZ`, predating the field; left as is
rather than silently rewriting an existing series' rows. Nothing committed — the phase-0
through phase-4 work is uncommitted in the working tree by the author's choice.

## 2026-09-15 — model sync, phase 5: exports by commodity group, and the «Экспорт» sheet cut loose from an external workbook

**What.** The last fact block of the GDP model still hand-loaded was the «Экспорт» sheet:
23 commodity groups by value (млн $) and physical volume, 2024–2025 still the January-2025
forecast formulas, and 396 formulas pointing at another workbook (`2355.xlsx` on the
author's Yandex.Disk) for world prices and sector volume indices.

**Pipeline.** Two datasets from the export workbook that already feeds EXPORTS and
OIL_EXPORTS_* (element 446905): `EXPORTS_VALUE_BY_COMMODITY_GROUP` (thousand USD) and
`EXPORTS_VOLUME_BY_COMMODITY_GROUP` (tonnes), monthly January 2019 – June 2026, 3 288 rows
each, `scripts/fetchers/bns_trade.py`, dispatched by a dataset-level `fetcher` key.
Groups are HS prefixes in `dictionaries/hs_export_groups.csv` — the model's grouping
(1001 wheat … chapter 15 fats and oils … chapters 86–89 transport equipment) — each the
sum of its 6-digit lines over the regional blocks, under the same per-month proof that
the regional rows reproduce the national total that OIL_EXPORTS_* uses (the two months
of September 2022 fail by 1.1–1.5 % and are skipped). TOTAL is the national row. The raw
copy is shared with the day's EXPORTS download when it exists. What the 6-digit file
cannot give and is therefore not offered: gas condensate (2709 00 100 0) and the
'основные товары' subset of petroleum products — `CRUDE_OIL` is all of 2709,
`PETROLEUM_PRODUCTS` all of 2710; natural-gas tonnes (published in m³ only).

**Model, step 12 — external links.** All 396 `[1]` formulas now point at this workbook:
rows 30–51 (prices) at the same series on «Внешние и внутренние факторы» (Brent row 2,
gas Europe 67, coal 65, wheat HRW 89, iron ore 116, metals 114–123, and for the rows the
sheet uses as year-on-year multipliers the y/y rows 134/141/142), rows 58–81 (ИФО) at the
same sectors on «ИФО_производ_регионы» (01.1–01.3, 07.1, 07.2, 05, 19, gas row 130, 24.2,
24, 01, 20, 30, GDP row 1399). Every correspondence was established from the rows' cached
2022–2023 values (all equal except BNS's later revisions of 2023 for 07.2 and 24.2 and of
2022 for 24: 100.5 vs 100) and from the formula form — a ratio-of-levels row gets a price
level, a direct-multiplier row a y/y index. Two rows changed source by design: crude oil
and petroleum products now take the Brent reference row 2 (99.8/82.6 $ for 2022–2023
instead of 99.21/82.16 from the old workbook). Rows 26/108 («Прочие») got the 2023
residual pattern for 2024–2025 and rows 2/109 became inputs; `excel_apply.ps1` gained a
`breaklinks` op and the link definition is gone. «Контроль» and every other sheet:
unchanged (the sheet is a satellite — nothing references it).

**Model, step 13 — facts.** Four mappings (`exports_total`, `exports_value_groups`,
`exports_volume_tonnes`, `exports_volume_thousand_tonnes`, `replace_formulas: true` by the
approved phase-5 plan): 126 checks, 116 cells rewritten — the total, 21 value groups and
20 volume rows for 2023–2025 (2023 was an earlier vintage of the same data: total 79 812
→ 79 138.8 млн $, oil 43 403 → 42 320, iron ore +3 %, transport +6 %; the 2024–2025
forecast formulas → BNS). Row identities hold to 0.000 (total = groups + «Прочие»); the
2026–2030 formulas chain on from the 2025 facts and the re-linked prices/ИФО (2026 total
now 94.0 bn $ against 86.5 before). Re-check 126 ok. Not mapped and left as the author's:
rows 10/92 (condensate), 11/93 (petroleum products), 91 (crude tonnes — linked to «Прогнозы
ЦГО», 71.0 Mt for 2024 against BNS 71.04 Mt) and 94 (gas volume). Gold tonnage in the
model (11.27 t for 2023) was not the customs figure (6.77 t) and is now BNS's. Journal
1 318 → 1 485 rows. Copy on Yandex.Disk replaced under a hash check (dceb4f43 →
73562144); the original is unchanged (3f5a1228). Tests 290 → 294.

**Not done.** Imports by group (the model does not use them). The «Экспорт» rows for
2026–2030 still carry the sheet's own price/volume mechanics — that is the author's
forecast, not a pipeline matter. Nothing committed.

## 2026-09-15 — de-duplication: eleven scalar series derived from the item-level layer, one download and one raw copy per source file

**Why.** A scan of all 431 scalar series (pairwise, by period, after normalising dates)
found no two that are literal copies of each other. It did find eleven that are exact —
or unit-scaled — copies of national items the item-level layer already produces from
the same BNS tables, fetched a second time by their own scalar fetcher, in several cases
from a source that had since gone stale. And the same source files were being
downloaded and archived several times a day: the 56–65 MB export workbook under three
indicator ids (EXPORTS, OIL_EXPORTS_VALUE, OIL_EXPORTS_VOLUME), the 22 MB industrial
cube under four, NBK forms once per series (formId 132 twice, 51 five times …) —
2.9 GB of byte-identical raw copies on disk by this date (git stores identical blobs
once, so the repository itself grew less than the working tree, but every clone and
every run paid for the copies).

**What changed.**
- `config/indicators.yaml`: `derived_from: {dataset, item, region, scale}` on IND_PROD,
  IND_PROD_MINING, IND_PROD_MANUFACTURING, IND_PROD_ELECTRICITY (← INDUSTRIAL_PRODUCTION_
  INDEX_BY_ACTIVITY IND/B/C/D), INVESTMENT (← INVESTMENT_BY_REGION TOTAL × 1e6), EXPORTS,
  OIL_EXPORTS_VALUE, OIL_EXPORTS_VOLUME (← EXPORTS_*_BY_COMMODITY_GROUP TOTAL/CRUDE_OIL),
  POPULATION_BNS (← POPULATION_AVG_BY_REGION ALL), EMPLOYED_TOTAL (← EMPLOYED_BY_REGION
  TOTAL × 1000), ELECTRICITY_PRODUCTION (← PRODUCTION_NATURAL_BY_REGION ELECTRICITY × 1e6).
  `scripts/update_derived.py` writes them after `update_dims.py` with the usual
  validation, revision log and metadata (the metadata names the dataset and item).
  Their fetchers (483 lines of `fetchers/bns.py`, including the trade-by-HS parser now
  superseded by `bns_trade.py`) and registrations are gone; the endpoints in
  `sources.yaml` are marked `derived` with the research trail kept.
- Verified before switching: on every common date the derived series equal the old ones
  to the last digit, with three explainable exceptions — IND_PROD_ELECTRICITY 2023
  (105.4 → 105.351, a BNS revision in the live table), POPULATION_BNS 2021 (19 000 987.5
  → 19 000 687, likewise), INVESTMENT (the table publishes million KZT, the cube full
  tenge: differences under 0.5 million on 8–15 trillion). ELECTRICITY_PRODUCTION was
  not a duplicate but a broken series: the Taldau figures for 2016–2020 were a thousand
  times the 2021–2024 ones (94 642 384 000 000 vs 115 078 200 000 "kWh"); the item-level
  table is consistent (million kWh) and differs from the sane years by 0.0002–0.09 %.
  Histories grew: IND_PROD 1990–2025 instead of 2009–2023, INVESTMENT 2003–2025 instead
  of 2016–2022, EMPLOYED_TOTAL 2001–2025, POPULATION_BNS 2009–2025, EXPORTS and the oil
  series 2015–2026 (BNS added 2015–2018 sheets to the workbook this month).
- `lib/raw_store.save_raw_bytes` returns the path that holds the bytes and, when another
  indicator archived byte-identical content the same day, returns that file instead of
  writing a copy (`same_day_twin`); fetchers record it as `raw_file` in their manifests.
  Every agency's `_download` (bns, nbk, minfin, imf; ardfm already had one) caches per
  process, so a file read by several indicators is requested once per run.
  The export workbook is now archived once a day under its old name `bns_exports_<date>`.
- Tests 294 → 299 (`tests/test_derived.py`: derivation, registry consistency — every
  scalar id is either fetched or derived, never both, never neither — raw dedup,
  download cache). Model sync unchanged (the model's POPULATION_BNS, EMPLOYED_TOTAL and
  EXPORTS values are the same numbers).

**Looked at and deliberately kept.** GDP_INCOME_METHOD equals the Q4 (year-to-date)
value of GDP_NOMINAL every year — two BNS measurements of one total, kept because one is
annual from 2000 and the other quarterly. The IMF WEO series that shadow national ones
(population, GDP, unemployment, inflation, debt) are different vintages with forecasts,
not copies. ANNUAL_INFLATION (NBK) and CPI_YOY (BNS) differ by up to 0.7 pp on the same
month — worth a look at the dating convention, not a duplicate. The lifecycle-tagged
frozen series (NBK banking ratios to 2024-04, PASSENGER_TURNOVER, per-10k health ratios)
stay: their successors do not cover the same periods or definitions.

**Not done.** The 2.9 GB of byte-identical raw copies already on disk were not deleted —
the repository's rule is that raw files are never removed, and git keeps them in history
regardless; they simply stop multiplying from here. Removing them from the working tree
is a one-line decision for the author.

## 2026-09-15 — raw store: byte-identical copies removed, one copy per distinct content from now on

**What.** The author asked for the old copies to go. 5 683 raw files (9.9 GB of 11.2 GB)
were byte-identical to another file archived for the same agency — the same workbook
under several indicator ids, the same PDF or form re-downloaded on days when the source
had not changed — and were removed from the working tree; every one of them maps to the
file that still holds its bytes in `data/raw/dedup_2026-09-15.json` (matched through git
blob ids — identical content is one blob — and, for twins added the same day, by byte
comparison), and the dated manifests of the removed files carry `raw_file` pointing at it.
Five legacy-.xls tables that the first phase-3 run had saved under both extensions were
restored by the verification pass (it looked for twins with the same extension), then
removed again once the .xls twins were confirmed byte-identical -- 5 688 files in all; the
check that every removed file has a surviving twin is part of the record. Nothing with distinct content was
touched. `data/raw` is now 1.39 GB.

**Rule going forward.** `lib/raw_store.identical_twin`: a download whose bytes are
already archived for the agency — any indicator, any day — is not written again; the
indicator's dated manifest records the download and names the file. Revised content still
produces a new dated file, and files already archived are never modified or removed by
the store. The MASTER-TASK rule reads as before with one clarification in README: raw data
is never edited and distinct content is never deleted.

**Note.** Git history still contains the removed copies (identical blobs are stored once
by git, so the .git directory was never as large as the working tree); shrinking clones
would need a history rewrite, which was not done.

## 2026-09-15 — model sync, phase 6: every number in the model has a source; the update calendar

**What.** The last phase of the loading plan: no number in the GDP model without a named
source, and a calendar of when each source moves next.

**Coverage.** `scripts/model_coverage.py` walks every literal number in the workbook's year
columns (repeated year headers inside sheets are ignored) and classifies it: claimed by a
`model_map.yaml` mapping, claimed by an entry in the new `config/manual_inputs.yaml`, or
unaccounted. First run on the phase-5 model: 67 075 numbers, 4 153 pipeline, 62 922
unaccounted — almost all of them history before 2023 and the input-output reference
sheets. Now: 66 656 numbers, 4 209 pipeline, 62 447 manual, 0 unaccounted
(`--strict` passes).

**Fourteen more contract mappings** for national totals the scan found unclaimed: the
labour block of «Прогнозы ЦГО» (labour force, employees, self-employed, unemployed, the
rate, the real-wage index) and its grain harvest; the national rows above the regional
blocks on «Факторы» (labour force, unemployed, unemployment rate, self-employed, urban
and rural population); the national fixed-investment volume index on «ИОК»; the section
deflators on «Дефляторы_производ_регионы» (2023 typed, 2024+ computed by the model —
controls within 0.25 pp). 111 checks: 99 ok, 9 applied, 3 controls. The nine are BNS
revisions of 2023 figures the ministries had supplied (labour force 9 378 → 9 534 thousand,
employees, self-employed, unemployed, rate 4.8 → 4.7, real wage index 100.3 → 102.7, grain
harvest 17 708 → 17 097 thousand tonnes) and the 2023 urban/rural population totals, whose
regional blocks had been revised in phase 2 while the totals above them stayed
(12 330 544 → 12 386 757; 7 569 780.5 → 7 513 567.5). Only those nine cells changed; every
other sheet and «Контроль» are byte-for-byte as before. Journal 1 485 → 1 495 rows. Copy on
Yandex.Disk replaced under a hash check (73562144 → b115ea6f).

**manual_inputs.yaml** — 45 entries. Per sheet: the history before 2023 (author's loads
from earlier BNS/NBK/WB/IMF publications, vintage not recorded — said so); the 2023 base
year below the section level on the production sheets (BNS January-2025 publication; the
pipeline has no regional detail below sections); «Прогнозы ЦГО» fact columns and forecasts
(PSER 2025–2029, January 2025; the rows with a BNS series are pipeline-checked); the Brent
agency forecasts (author's collection, January 2025); the inflation corridor and the
«значение для дефлятора» assumption; the budget/private investment split from the express
releases (the author's 14.09 decision); the export rows the 6-digit workbook cannot give;
the price-index constants; the input-output tables of 2023 on Лист2/Лист3 and the
productivity satellite (no formula references them). Five entries are `kind: review` —
literal numbers where a formula or a source would be expected: «Зерна, $/м.т.» = 185 on
«Факторы»; ИФО 2024 of coal (99.2) and of the electricity subsections 35.1–35.3 among
empty/formula cells; the pair 6 310 / 2 580 for «г.Алматы» in three derived sheets. These
are the author's to resolve; nothing was changed.

**Calendar.** The BNS dynamic tables state «Дата последней/следующей актуализации» in their
Метаданные sheet; `bns_dims.fetch` now reads both into `publication_date` and
`next_update_date` of the dataset metadata (28 of 40 tables carry them; the legacy .xls
tables, 4446 and 5546–5549 do not). `config/calendar.yaml` adds the rhythms without a
machine-readable date (CMO 2 October 2026; Pink Sheet and STEO monthly; WEO April/October;
PSER 2027–2029 — not yet received; the express releases; the IO tables) and the refresh
procedure. `scripts/build_calendar.py` writes `project_knowledge/CALENDAR.md` — 68 series
the model reads, next dates, overdue flags, the manual blocks with their refresh rules —
and `update_all.py` rebuilds it daily. Tests 299 → 303.

**Not done.** Extending the fact-year checks into history (the pipeline reaches 1960 for
World Bank prices, 2000–2010 for BNS) would turn most `history` entries into pipeline
coverage — a `years` change in `model_map.yaml`, but the author's call, since the history
would then be rewritten to today's vintages. Nothing committed to main yet.

## 2026-09-15 — two corrections to the de-duplication notes

**ANNUAL_INFLATION vs CPI_YOY — a dating convention, not a discrepancy.** The 0.7 pp
"difference on the same month" reported on 2026-09-15 disappears entirely when the NBK
series is shifted one month back: ANNUAL_INFLATION is event-dated by the day the figure
appeared on the NBK widget (2026-09-02 carries August 2026), CPI_YOY by the reference
month. Shifted, all 8 common points equal CPI_YOY − 100 to the decimal. By content it is
BNS's own index republished by the NBK; it stays as the deliberate independent cross-check
its metadata describes, with a `dating_note` in indicators.yaml so nobody compares the two
on the calendar date again.

**"15 GB of deleted blobs in git history" — wrong, withdrawn.** Git stores one blob per
content, so the byte-identical raw copies removed on 2026-09-15 never occupied extra
space in `.git`: the packed history is 39 MB (1.5 GB of unique blob content, mostly
daily NBK JSON, delta-compressed), and a history rewrite would free 6 MB — 23 blobs whose
content is no longer at HEAD. The large files live in Git LFS (`data/raw/bns/*.xlsx`),
which also de-duplicates by content and which a history rewrite does not shrink on GitHub
at all (LFS objects are only removed with the repository). A rewrite would change every
commit hash, force every clone to be re-cloned and invalidate the hashes quoted in this
log for no gain. Not done, and not recommended.

## 2026-09-15 — ANNUAL_INFLATION retired; CPI_YOY (BNS) is the headline inflation series

The author's decision on the dating finding above: the NBK's release-dated republication of
the BNS index adds nothing to CPI_YOY, so it is retired — the indicator entry, the fetcher
(`fetch_annual_inflation`) and the registration are removed, the sources.yaml endpoint is
marked `retired` with its research notes kept, the processed file and metadata are deleted,
the raw downloads stay. 430 scalar indicators remain. Year-on-year inflation = `CPI_YOY − 100`
for the reference month.

## 2026-09-15 — first CI run of the new pipeline: what it showed, and two source changes

**The run** (workflow_dispatch on cf83162e): pipeline 65 minutes, tests 303/303 on the
runner, commit `99213b13` — the first automated commit since 9 September. The daily runs
of 10–14 September had all died with "No space left on device": the runner could not hold
the working tree with its 11 GB of duplicate raw copies (checkout alone took 70 minutes on
the 14th and the pipeline never finished). After the de-duplication the checkout took 13
seconds, and the store's one-copy rule held on the runner too (every re-downloaded
unchanged file was recognised and not stored again).

**410 datasets ok, 67 stopped as structural changes** — two of them real, and one of the
two fixed here:

1. *NBK open-data forms (65 series: balance of payments, external debt, loans, remittances,
   payments, OTC and KASE turnover, reserves ratios).* The archived pages of 9 and 15
   September are identical except that every row now carries a new technical field
   `row_id`. The fetchers pin a series by requiring "no other classification field set",
   and treated `row_id` as one. `NON_CLASSIFICATION_FIELDS` in `fetchers/nbk.py` now lists
   it beside `report_date` and `amount`; verified offline on the archived pages and live
   on three of the series. Tests 303 → 305.
2. *BNS element 446905 (the export workbook by HS line).* From about 07:50 UTC the element
   serves a 23 KB workbook with only the description sheet and an annual per-region summary
   — no monthly sheets — both from the runner and from Almaty; at 06:13 the same URL had
   given the full 65 MB file (grown by the 2015–2018 sheets), and the import element
   still gives its full 144 MB file. The parser stops loudly on a workbook without year
   sheets (message made explicit), the two commodity-group datasets and the three series
   derived from them keep the last good data (through June 2026). Whether the element is
   being regenerated or has been re-pointed is not known; recorded in sources.yaml, no
   replacement id asserted. Watch the next daily reports.

The remaining "structural changes" of that report are the same two as on 9 September.

## 2026-09-15 — second CI run (a834d5e1 → bf22916c): 460 ok, 17 stops; the last 13 NBK stops explained

The row_id fix brought 52 of the 65 NBK series back. The remaining 13 were four more
changes the API made the same day, each visible by comparing the archived pages with the
previous edition (values identical throughout):
- formId=41 (OTC exchange rates and turnover, 6 series): a new `periodicity` field, "monthly"
  on every row. Rule added to `_fetch_nbk_exact_row`: a field uniform across the whole form
  cannot tell series apart and is not a classification.
- formId=35 (KASE rates and turnover, 4 series): a new `period` field holding a month label
  that only repeats report_date ("apr", "30 jun"). Listed in `FORM_IGNORE_FIELDS`.
- formId=476 (gold bullion sales, 1 series): a new `weight` field, the total weight of the
  pieces sold in the quarter — a second measure, not a dimension. Listed there too.
- formId=412 (remittance transaction counts, 2 series): the all-currency rows, which used to
  have an empty `currency_code`, now say "Total"; pinned in `REMITTANCE_COUNT_MATCH` after
  checking that the 116 common values are unchanged to the last digit.
All 13 fetch live again. Tests 305 → 308. Still stopping: the two Minfin pension series
(since 9 September, unrelated) and the two BNS export datasets (element 446905 still
serving the 22 KB stub at 09:35 UTC).

## 2026-09-15 — the two Minfin pension series: table 27 is dated 1 January only half the year

PENSION_CONTRIBUTIONS_RECEIVED and PENSION_CONTRIBUTIONS_ARREARS had stopped since 9 September
(the first daily run to open the 'as of August 1, 2026' bulletin). Cause: table 27 of the
bulletin is rebuilt twice a year, not with every edition — the editions published from
about February to July carry the figures as of 1 January (the annual series these two
indicators are), the editions from August on carry the figures as of 1 July (half-year
receipts, mid-year arrears); the August edition switched while the 'as of July 1, 2026' one
still showed 1 January, and the title does not say which. The fetcher looked only at the
newest edition and only for «на 1 января». It now opens the editions newest-first (at most
eight, 1.2–1.5 MB each, cached per process) and takes the first whose table 27 is dated
1 January; the manifest lists the mid-year editions it skipped. The 1-July figures are not
stored — a half-year variant would be a separate indicator with its own semantics
(year-to-date receipts), not a silent change of this one. Verified live: both series return
their 2025 and 2026 points from the July-1 edition (2 448 612.9 / 2 548 511.5 and
3 287 315.7 / 4 486 885.8 million KZT). Tests 308 → 311.
