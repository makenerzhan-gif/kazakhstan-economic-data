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
