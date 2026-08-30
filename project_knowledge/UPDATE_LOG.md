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
