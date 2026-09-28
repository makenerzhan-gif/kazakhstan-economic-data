# Update Log

Recent entries, oldest first; append new ones at the end. Entries from 2026-08-30 to «2026-09-26 — lagging series: bank soundness, Minfin general government, passenger turnover» are in docs/UPDATE_LOG_ARCHIVE.md in the
repository (not synced into the Claude Project). When this file grows past ~60 KB, move the oldest entries there.

## 2026-09-26 — a failed dataset no longer blocks the daily run

`update_all.py` used to stop the unified rebuild and the commit on any single `error` (2026-09-25: one BNS file
format change held back ~660 healthy series). Every updater logs `error` before writing, so a failed dataset
keeps its previous processed file and unified values; the run now continues, lists the failures at the top of
the update report and raises one GitHub Actions warning per failure (plus the job summary). It still stops when
more than 20 % of datasets fail — an outage or a shared-code bug. Test: `failure_gate` in
tests/test_lagging_series.py.

## 2026-09-26 — debt structure completed for the sovereign-rating models: 515 -> 519 indicators

**Why.** An independent check of the Fitch / Moody's / S&P input sheets (project «Проект
обновление данных в моделях») found that the foreign-currency share of government debt divided
the Government's external debt (row 1.2 of the bulletin's «табл 22 кв») by GOV_DEBT — the
«Total State and State Guaranteed debt» line (sections I + II + III, i.e. including the
National Bank, local executive bodies and guarantees) — and took the 1 October snapshot as the
year's value. A like-for-like denominator, the National Bank row and a general-government
interest figure were missing from the dataset.

**Minfin (4), all from documents the pipeline already reads daily:**
- CENTRAL_GOV_DEBT — section I, row 1 «Долг Правительства Республики Казахстан» (36.82 trillion
  KZT at 2026-07-01; = GOV_DEBT_DOMESTIC + GOV_DEBT_EXTERNAL exactly, but 22 dates from
  2020-01-01 against the snapshot documents' 11).
- CENTRAL_GOV_DEBT_EXTERNAL — row 1.2 in the sheet's tenge column (8.35 trillion), the tenge twin
  of GOV_DEBT_EXTERNAL_USD; kept as its own id for the same coverage reason.
- NBK_DEBT — row 2 «Долг Национального Банка» (2.93 trillion at 2021-01-01, 0 by 2025-07-01,
  blank from 2026-01-01 — the parser skips blanks). Section I is already consolidated
  (I = row 1 + row 2 + row 3 − row 3.1, verified to the cent), so general-government debt on the
  bulletin's own definitions is section I − NBK_DEBT; guarantees (II, III) are contingent.
- STATE_BUDGET_DEBT_SERVICING — «табл 3», functional group 14 «Обслуживание долга» of the STATE
  budget (1.87 / 2.23 / 2.66 trillion for 2023–2025); the excess over the republican-only
  GOV_DEBT_SERVICING (57.5 / 50.3 / 52.6 bn) matches the local budgets' own row 14 in «табл 12»
  to within 1 bn.

**Parser change, shared by every «табл 22 кв» series.** In the 2020-01-01 column the tenge cells
of rows 2, 3, II and III are blank while the USD cells are filled (NBK: 8,968.4 mln USD) — a
blank there is not a zero. `_fetch_debt_structure_row` now converts such a cell at the sheet's
own implied rate for that date (section I row KZT / USD, 381.2 for 2020-01-01 — the II./III.
anchor rows are themselves blank in tenge there) and appends the converted dates to the dataset
note; a cell blank in both currencies is still skipped. LOCAL_GOV_DEBT and STATE_GUARANTEED_DEBT
thereby gain their 2020-01-01 point (21 → 22 dates each); nothing else in those series changes.

**Cross-check against IMF WEO.** General government gross debt (GGXWDG, 24.56% of 2025 GDP =
38.74 trillion KZT) equals section I − NBK_DEBT + II + III at 2026-01-01 (36.44 − 0 + 2.29 +
0.006 = 38.74): the WEO series includes state guarantees but not the National Bank's debt — the
two coincide with I + II + III only in 2025, when NBK_DEBT is already zero.

Tests: full suite 459 passed after rebasing onto main (`tests/test_minfin_debt_structure.py`: section-anchored row lookup, the USD
fallback, the section identity with row 3.1, the «табл 3» annual columns). Data files and the
unified dataset were rebuilt locally for the nine «табл 22 кв» / «табл 3» indicators only;
the scheduled CI run refreshes the rest.

## 2026-09-26 — NBK form downloads archived in canonical form; 101 same-content copies removed

**Why.** The insurance form (formId=132, 13.7 MB, read by INSURANCE_PREMIUMS_GENERAL/LIFE) was archived
again on nearly every run since 2026-08-31, often several times a day: 102 files, 4 distinct contents.
The rows were the same and in the same order; what changed on every call was the per-page `columns`
block — the API labels `residency` "Residency of institutional units" on some pages and "residency"
(null before 09-15) on others, in a new random mix each time — so the byte-level dedup of
`lib/raw_store` never matched. Every other form already had one file per content; `row_id` is stable.

**What.** `fetchers.nbk._fetch_nbk_form_paginated` now archives the canonical form of the pages
(`scripts/lib/nbk_pages.py`): all rows unchanged and none dropped (repeats kept), sorted by
report_date then full row content; envelope fields once, `n_pages`; distinct column entries sorted;
sorted keys. Only page boundaries and the API's row order are not kept. The manifest records
`raw_file`, `raw_format` (`nbk-open-data-form/canonical-v1`), `raw_normalisation`, `rows_archived`.
Checked live: a second same-day run stores no new file. `scripts/dedup_raw.py --nbk-forms` groups the
NBK form files by canonical content (keeping a canonical file where one exists, else the earliest),
removed 101 files / 1 307 MB (insurance 98, the 324 and 481 forms under CURRENT_ACCOUNT_BALANCE one
each, replaced by today's canonical copies) and re-pointed their manifests; a manifest without
`raw_file` is now taken to name the file of its own stem. Record: `data/raw/dedup_2026-09-26.json`
(`nbk_forms_removed`). Five new tests (`tests/test_nbk_pages.py`).

**Also.** The five BoP series (CURRENT_ACCOUNT_BALANCE, BOP_GOODS/SERVICES_BALANCE, BOP_PRIMARY/SECONDARY_INCOME)
read form 324 and, for 2000–2019, form 481 under the same id, so the 481 download overwrote the dated manifest
of the 324 one and was filed as a same-day "revision" (`_HHMMSS`). `_bop_history` now archives 481 under
`<ID>_HISTORY`: two manifests per series per day, no false revision; the series are unchanged (104 quarters).

**WITS.** Every WITS answer (7 series) was archived again on every run although only `header.prepared`, the
time WITS built the answer, differed. `gravity._save_raw` was meant to skip such answers, but
`raw_store.latest_raw_file` returned the dated *manifest* (it sorts after the `.json`), so the check never
matched. `latest_raw_file` now never returns a manifest, and `_save_raw` still writes the day's manifest,
naming the file that holds the data. `dedup_raw --wits` removed 14 copies (record: `wits_removed`). Seven
manifests of 2026-09-25 named files from a second run that day that were never committed; they now name
the file archived that day, with a note, and are listed under `wits_never_committed` (not as removals —
their bytes are unknown). No dangling manifest left. Checked live: two WITS runs, no new file.

The CI run of 2026-09-26 09:45 (old code) added one more insurance copy (`…_094522.json`); removed on
merging main, same record (116 files in all).

**First CI run on the new code (2026-09-26, run 36239472600).** No new insurance or WITS copy. It archived
38 NBK forms for the first time in canonical form (18.4 MB); each held the same data as the form's last
old-format file, so those 38 old copies (18.5 MB) were removed with `dedup_raw --nbk-forms` (same record).
From now on an NBK form or WITS answer is stored again only when its data change.

## 2026-09-26 — National Fund receipts by tax and payment: 519 -> 534 indicators

**Why.** The pipeline had the National Fund's assets, portfolios and the NBK's monthly transfer
flow (from 2024), but not what flows into the Fund by tax. CAEM (`NFRK_R_oil_*`) and the fiscal
blocks of the models need the oil-sector taxes; the CAEM mission file stops in 2023 and has holes.
Sources were surveyed beforehand (`Справочники_МВФ/sources_nf_receipts.md`).

**Minfin (15 series, monthly, year to date, million KZT; source thousand KZT).** Every «Statement
of receipts and application of the National Fund … as of 1 <month>» / «Отчет о поступлениях и
использовании Национального фонда» of activity 7294 on gov.kz (all listing pages; 106 documents,
reports as of 1 Feb 2018 … 1 Jul 2026, all parsed). Series: NF_OIL_CIT_YTD, NF_EXCESS_PROFIT_TAX_YTD,
NF_BONUSES_YTD, NF_MET_YTD, NF_RENT_TAX_EXPORT_YTD, NF_PSA_SHARE_YTD, NF_PSA_ADDITIONAL_PAYMENT_YTD,
their line NF_OIL_DIRECT_TAXES_YTD, NF_OIL_OTHER_RECEIPTS_YTD (fines, damages, other non-tax),
NF_OIL_RECEIPTS_YTD (the two lines added), NF_PRIVATIZATION_YTD (privatization + transfer of
national-company assets to the competitive environment; the sale of bank-loan-portfolio assets is
not in it), NF_INVESTMENT_INCOME_YTD (the receipts line «investment income from the Fund
management» only: the NBK-approved income of the last approved period, a quarter to three quarters
behind the month; December is the full year only in 2018, 2020, 2021 — nine months in 2019 and
2023, 30.3 bn in 2022 — and there is no December 2024 or 2025, the approved annual reports book no
investment income in receipts; their item «Investment income, total», the NBK's full-year result
with the exchange-rate revaluation, is not used), NF_GUARANTEED_TRANSFER_YTD,
NF_TARGETED_TRANSFERS_YTD and NF_TRANSFERS_YTD. The flow series NATIONAL_FUND_TRANSFERS (NBK, from 2024-02) stays; the Minfin
total is year to date by type from 2018 (2025: 5 250 bn against 5 201 bn summed from NBK months).
- Lines are found by EN/RU label (rows moved: budget-loan repayment lines in 2025–2026, investment
  income moved out of receipts in the approved annual reports); a line printed blank is zero.
- The period is read from the sheet heading, not the listing title (25467 says 2020 for 2019;
  26492, listed as 1 December 2018, is a second copy of 1 November). Document 638881 is headed
  «1 March 2024» but its numbers lie between 1 March and 1 May and it was posted on 2024-04-03:
  `DOC_PERIOD_OVERRIDES` makes it 1 April 2024. The approved annual reports for 2018 (26493) and
  2024 (866047) stand in for the missing reports as of 1 January 2019 and 2025. The approved 2023
  report (677412) has lines 21–23 one row up (land sales 53 349 = KGD code 303102 stand as
  privatization): `DOC_LINE_EXCLUSIONS` takes 2023 privatization from the 1 January 2024 report.
- Four identities on every report (2 thousand KZT): seven taxes = direct taxes, four items =
  other oil-sector receipts, first-level lines = «Receipts, total», lines = «Application, total». A
  failing report is left out and named in the note. Two documents are repaired first
  (`NF_DOC_FIXES`, each fix checked against the labels it expects): in 866029 (as of 1 July 2025,
  the re-issue with the half-year income) every value from the second budget-loan line to the
  management expenses sits one row too high — found by the two total identities, the only report
  failing them; moved back, 2025-06 reads guaranteed transfer 2 000 bn (was 1 120), targeted 1 120
  (was 23.7), privatization 0.608 (was 1.0), investment income 2 480.8 (was 0). In 946754 (as of 1
  January 2026) 23 000 000 thousand stands against «transfer to the competitive environment» and
  the bank-asset line is missing; the approved report for 2025 (Decree No. 1328, NBK file 135446,
  p. 4) has 2.5 blank and 2.6 «sale of assets by the organization improving banks' loan
  portfolios» = 23 000 000: 2025-12 privatization is 1.284 bn (was 24.284). All 106 pass.
- The daily run reads a report from `data/raw/minfin/` when its id is archived there with the size
  gov.kz writes into the upload path (`…_original.36864.xls`), and downloads only new or re-uploaded
  ones (checked: 0 of 106 downloaded on the second run).
- Missing months: May 2018, November 2018 (no report as of 1 June / 1 December 2018), April–May
  2026 (not published). Not interpolated.

**History 2002–2017 (the seven taxes).** KGD «Динамика поступлений налогов и платежей в
Национальный фонд», one by-tax workbook per year, loaded once by the new
`scripts/load_nf_receipts_history.py` into `data/reference/nf_receipts_kgd_history.csv` (1 433
rows; workbooks archived as `minfin_nf_receipts_history_kgd_<year>_2026-09-26.*`). Rows by
Russian label; a workbook is kept only if its tax rows add up to «ИТОГО по налоговым
поступлениям» in every month — 2005 fails (misplaced numbers) and there is no 2006 file; 2003–2004
start in August. The fetcher prepends KGD months before 2018-01 only while KGD equals Minfin in
every shared December (2018–2024: 7 of 7 for all seven taxes). Within the year KGD and Minfin
differ now and then by payment timing (CIT: 21 of 79 months equal, largest gap 2.3 bn; rent tax
largest 12.3 bn); the note says so.

**Cross-checks (December, bn KZT).** Against the source note: 2022 CIT 2 266.198, MET 1 582.031,
PSA share 1 477.397; 2023 1 532.974 / 1 282.495 / 1 035.543; 2024 1 265.822 / 680.875 / 1 202.176;
2025 1 300.317 / 899.223 / 1 045.387 — all equal. Against CAEM `nfrk_detail.csv` 2014–2023, all
seven taxes: largest difference 0.000008 bn. CAEM's holes are filled here: PSA share 2014 (357.477),
MET and PSA share 2017 (626.350, 285.893), also EPT 2008/2012 and PSA share 2008–2009. 2002–2004
and 2007–2013 equal CAEM wherever both have a value.

Tests: `tests/test_minfin_nf_receipts.py` (25: synthetic sheets with moved rows and RU labels, the
four identities one by one, blank = zero, investment income only from the receipts line, the
heading → period table incl. the typos, the two document fixes on the archived reports and their
label guard, the period override, the line exclusion, the latest posting winning, a failing report
left out, the archive read, December = KGD's January–December column for 2023 and 2024, the
December overlap rule, the KGD workbook identity). Full suite: 495 passed. Only the 15 new fetchers
were run live; the unified long file gained 2 285 rows, the wide file 15 columns, no existing row
or cell changed (against origin/main dfc74557).

## 2026-09-27 — BNS CPI publication «Индекс потребительских цен и производные показатели» (Т-15-02-М), 2004–2026

**What.** Ten item-level datasets (config/dims.yaml, `fetcher: bns_cpi`), monthly, one per
comparison base: `CPI_DETAIL_{MOM,YTD,YOY,AVG_YOY}` (total, food/non-food/services, the COICOP
divisions, ~250–300 individual goods and services a year, the three core-inflation baskets, and the
total and groups for every region), `RETAIL_PRICES_{MOM,YTD,YOY,AVG_YOY}` (retail price index,
goods, national and regional, from 2022-10) and `CPI_CONTRIBUTION_{MOM,YTD}` (contribution to CPI
growth, p.p., from 2020-01). 91 312 rows in CPI_DETAIL_MOM alone, 643 item codes, 2004-07 … 2026-08.

**Sources.** stat.gov.kz → Экономика → Цены → Электронные таблицы: 19117 (Т-15-02-М, 47 editions
2022-10 … 2026-08; read daily, the latest three editions and any month not yet stored), 166775
«Индекс потребительских цен в РК» (284 editions 1999-05 … 2022-12; the 222 from 2004-07 read — the
earlier ones are html text tables in a pre-COICOP grouping) and 27168 «Вклад отдельных
составляющих…» (36 editions 2020–2022). History loaded once by `scripts/backfill_cpi_publication.py`
(needs `unar` for the rar archives; the archives are not added to data/raw).

**Layouts.** Russian labels 2004–2007; «Kazakh\nRussian» in one cell 2008–2012; both languages on
one line or Kazakh alone 2012–2019 (the Russian label recovered from the clean editions); Kazakh
in column A and Russian in the last column 2019–2022; Russian from 2022-10. Columns are read by
their header text (the dative month and year), not position; the quarterly columns and the fixed
December base are not kept. Fixed: BNS headed the year-on-year column «июню» in July 2024 and
July 2025 and «январю 2025г.» in February 2026 (read as year-on-year, the manifest says so); a
March 2008 row labelled «Продовольственные товары» that is alcohol and tobacco; «Мужская»,
«Женская», «Детская», «Колготки», «Сорочка верхняя» printed twice (clothing / footwear) are
qualified by the heading they sit under; May 2021 of the contribution table is Kazakh-only and
takes its labels from April/June 2021 (46 identical rows).

**Checks.** Equal to the scalar CPI, CPI_YOY, CPI_YTD, CPI_FOOD(_YOY), CPI_NONFOOD(_YOY),
CPI_SERVICES(_YOY) and CORE_CPI_* on all common months (2011-01 … 2026-08; one 0.1 difference,
CPI_FOOD_YOY 2022-06). The two publications agree on all 4 052 values of 2022-10 … 2022-12. The
contribution of «Товары и услуги» equals CPI m/m − 100 within 0.06 every month. Left as published
and reported: retail food YTD, table 4 against table 5, February–June 2026 (0.7–0.8 apart);
housing-and-utilities contribution printed twice with different values in 2024-08 and 2025-04;
retail avg-YoY column of February 2026 (cereals 86.1 against 107.8 y/y).

Tests: `tests/test_bns_cpi.py` (35). Full suite: 530 passed. macro_dims_long.csv.gz grows from
3.1 to 5.3 MB.

## 2026-09-27 — IMF BOP, IIP and GFS, and every WDI series for Kazakhstan

**What.** Twelve item-level datasets (config/dims.yaml):

| Dataset | Source (IMF SDMX 3.0 / World Bank) | Series | Period |
|---|---|---|---|
| `IMF_BOP_QUARTERLY` / `_ANNUAL` | IMF.STA/BOP, BPM6, million USD | 853 / 894 | 1995Q1 – 2026Q1 / 1995 – 2025 |
| `IMF_IIP_QUARTERLY` / `_ANNUAL` | IMF.STA/IIP, positions, million USD | 464 / 462 | 1998Q1 – 2026Q1 / 1997 – 2025 |
| `IMF_GFS_OPERATIONS_KZT` / `_PCT_GDP` | GFS_SOO: revenue, expense, net lending, financing, by subsector | ~1 540 | 1992 – 2023 |
| `IMF_GFS_COFOG_KZT` / `_PCT_GDP` | GFS_COFOG: expenditure by function and subsector | 566 | 1997 – 2023 |
| `IMF_GFS_BALANCE_SHEET_KZT` / `_PCT_GDP` | GFS_BS: financial assets and liabilities by instrument | ~440 | 1992 – 2023 |
| `IMF_QGFS_KZT` | QGFS: cash sources and uses, S13 and S1311B, billion KZT | 96 | 1999Q1 – 2025Q4 |
| `WDI_KAZ` | World Bank WDI, every non-empty series for KAZ | 1 329 | 1960 – 2025 |

New `scripts/fetchers/imf_dims.py` (fetcher `imf_sdmx`): one generic reader for any IMF dataflow —
series key with wildcards, the dimensions that form the item code (`NETCD_T.CAB`, `S13.G1_T`),
English names from the dataflow's own codelists (structure query, references=all), a divisor
(USD → million USD, KZT → billion KZT). Quarterly flows dated at the quarter's first day, positions
at its last day. The IMF data are re-downloaded once a week (`REFRESH_DAYS`; the full set takes
~6 minutes), the stored records returned in between. `gravity.fetch_wdi_country` pages through the
World Bank sources API (source 2, KAZ, 5 pages × 20 000). Raw answers archived gzip-compressed.
GFS 1972–1991 (zeros) dropped.

**Checks.** IMF current account = NBK CURRENT_ACCOUNT_BALANCE in 94 of 104 common quarters;
2023Q1–2025Q2 differ by 14–350 mn USD (NBK revised them, the IMF's BOP not yet — NBK stays the
source for the headline balances). IMF net IIP = NBK IIP_NET on all 22 common quarters (one day
earlier). WDI nominal GDP = WEO nominal GDP 1994–2024 within 0.1 %. GFS general government:
revenue − expense − net investment in nonfinancial assets = net lending every year 2010–2023.
GFS revenue is NOT the WEO revenue series (2023: 27 897 against 26 253 bn KZT — different coverage
of the National Fund's income); both kept.

Tests: `tests/test_imf_dims.py` (14). Full suite: 544 passed. macro_dims_long.csv.gz 5.3 → 7.6 MB.

## 2026-09-27 — history for the fiscal, core-inflation, retail and credit blocks

Asked for: the budget monthly and quarterly before 2025, core inflation before 2023, retail
volume by goods group, credit by type before 2022, and the CPI detail visible in the Project.

**Budget.** The Minfin monthly Statistical Bulletins are online back to January 2019 (90 xlsx,
found by title search; the budget direction's listing shows only the latest ~14). New
`scripts/backfill_minfin_bulletins.py` read them all once (`minfin.BULLETIN_ARCHIVE`); every
bulletin series now keeps that history and the daily run lays the listed editions over it
(`_with_history`). Табл 3's January-to-month column and row labels are found by header text (the
2019-2021 layout had them in other columns, with quarterly columns in between); a «YYYY ж. есеп»
header over quarterly columns is no longer read as an annual figure. Result: STATE_BUDGET_*_YTD
2019-01 … 2026-07 (80 months, was 14), the 20 other bulletin series from 2019, annual state and
local budget from 2016; new quarterly STATE_BUDGET_REVENUE_Q / _EXPENDITURE_Q / _DEFICIT_Q,
2019Q1 … 2026Q2, discrete quarters from the January-to-month figures and the annual report.
Checks: on the 14 months stored before, every value is unchanged; the derived quarters equal the
quarterly columns the 2020-21 bulletins printed (2019Q1-Q3, 2020Q1-Q4) to the unit; the four
quarters add to the annual report; revenue − expenditure − lending − financial assets = deficit
every month except 2021-09 (90 bn apart in the bulletin itself, source_issues). The general
government quarterly cash operations 2008Q1 … 2025Q4 were added this morning (IMF_QGFS_KZT).

**Core inflation.** CORE_CPI_YOY_EX3 / CORE_CPI_MOM_EX3 from 2011-01 (were 2023-01): Taldau 703082,
the same «без фруктов и овощей, бензина и угля» basket under its pre-2023 index. Its Oct-Dec 2022
equal the Т-15-02-М tables to the rounding; twelve chained m/m reproduce y/y within 0.6 in all 132
months. The seven-component basket has no pre-2023 series on Taldau.

**Retail.** RETAIL_TRADE_INDEX_MONTHLY from 2016-01 (Taldau 702041; April 2026: 104.96 there, 105.0 in
the bulletin, which wins); new RETAIL_TRADE_INDEX_FOOD_MONTHLY, _NONFOOD_MONTHLY (y/y) and
RETAIL_TRADE_INDEX_YTD (January-to-month), 2016-01 … 2026-04. October 2025 is missing on Taldau.

**Credit.** New BANK_LOANS_STB_{TOTAL, KZT, FX, SHORT_TERM, LONG_TERM, LEGAL_ENTITIES, INDIVIDUALS,
BUSINESS, HOUSEHOLDS}: NBK «Кредиты экономике от БВУ (исторические данные)», end of month, 1996-01 …
2026-08 (business/households from 2003), dated as the money stock (end of month m = 1st of m+1). The
currency, status and business/household splits add to the total every month; households equal form
445's individuals in all 44 common months. Short-term 2000-08 carries an extra digit (source_issues).
No official time series of subsidised («льготное») lending was found: NBK's open data has only the
state agricultural lenders' portfolio (form 59, quarterly from 2025); Damu and Baiterek publish
annual reports only.

**Project.** `project_knowledge/latest/cpi_detail_latest.csv` (38 KB): the CPI publication's latest
month, per item and region, indices and contributions.

Tests: `tests/test_history_extensions.py` (9).

## 2026-09-27 — supply and use by product and region: production, trade, domestic use

Asked for: production, exports, imports and domestic consumption in physical and value terms,
by industry/product and by region. All new data are item-level datasets
(config/dims.yaml → data/unified/macro_dims_long.csv.gz).

**Trade by commodity and region** (the BNS customs workbooks 446905/446906, monthly 2015-01 …
2026-07, both flows, thousand USD and tonnes). EXPORTS_/IMPORTS_{VALUE,VOLUME}_BY_HS_CHAPTER:
the 96 HS chapters, national. EXPORTS_/IMPORTS_{VALUE,VOLUME}_BY_REGION_HS_SECTION: 21 HS
sections × 20 regions. EXPORTS_/IMPORTS_VOLUME_BY_REGION_PRODUCT: 19 commodities (coal, crude,
petroleum products, ores, cement, steel, ferroalloys, non-ferrous metals, flour, sugar,
sunflower oil, fertilisers) by region. Each file is read once for all its datasets
(fetchers/bns_trade.scan); every group is re-checked against the published national and
regional totals. September 2022: the national rows are 1-4 % below their own regions
(source_issues trade_national_row_2022_09); the Almaty-city import block misses its heading
by ≤0.003 % in four 2023 months (tolerance now 0.01 %). Region = where the trader is registered.

**Resources and use, national, physical units** (BNS publication 19065, archive 72035; 85
editions read by scripts/backfill_resource_use.py). RESOURCE_USE_MONTHLY (the month),
RESOURCE_USE_YTD (January to the month) 2018-03 … 2026-07, RESOURCE_USE_ANNUAL (final, 2021-24):
~270 industrial products, grain and vegetables, socially important foods (315 in all) —
resources, production, imports, use, exports, sales on the home market. Checked: coal
January–July 2026 production 63 029 kt, exports 17 833 kt, wheat exports 4.95 Mt — the
edition's own figures; resources = production + imports in 99 % of rows. BNS revises past
months only inside the cumulative figures (wheat exports January–March 2026: 3.66 Mt first,
~2.6 Mt implied by July), so for totals use the YTD dataset.

**Annual balances.** AGRI_BALANCE (publication 19517, 2017-2025): grain, grain products, meat,
milk, eggs, potatoes, fruit, sugar beet, sunflower seed, vegetable oil — stocks, production,
imports, feed/seed/processing/losses, exports, personal consumption (total and per head),
stocks; grain 2024: production 25.2 Mt, exports 8.25 Mt, feed 3.97 Mt. ENERGY_BALANCE_TJ /
_NATURAL (publication 19275, 2021-2025): the fuel-energy balance, ~40 fuels × ~85 flows (supply,
transformation by plant type, own use, final consumption by 20 sectors); production + imports
+ exports + bunkers + stock change = total primary supply every year (2025: 3.35 million TJ).
No regional energy balance is published after 2020.

**Industry by region, monthly** (Taldau, 2020-01 onward). INDUSTRY_OUTPUT_BY_REGION_MONTHLY
(701592): output in million KZT, 20 regions × ОКЭД sections and divisions (31 items); the
regions add up to the national figure exactly. INDUSTRY_PRODUCTION_PHYSICAL_BY_REGION_MONTHLY
(701608) and INDUSTRY_SHIPMENTS_BY_REGION_MONTHLY (701622, total and to the domestic market):
69 products (BNS's main-products list and further КПВЭД products), unit in item_name.
Re-downloaded weekly (refresh_days). REGIONAL_PRODUCT_BALANCE: derived production − exports +
imports by region for the 19 commodities, with the domestic shipments beside it — a cross-check,
not a statistic (BNS publishes no regional product balance).

**Project.** `latest/resource_use_latest.csv` (78 KB): the resources-and-use table for the
latest January–month against a year earlier.

Tests: `tests/test_supply_use.py`.

## 2026-09-27 — the budget back to 2013, December, gaps, non-oil deficit before 2022

**Pre-2019.** Minfin keeps the same monthly Statistical Bulletin for 2003-2018 as one RAR per year
(«Статистический бюллетень за 2017 год (12 месяцев)»); 2013-2018 are xls/xlsx with the tables of the
current editions. `scripts/backfill_minfin_bulletins.py --yearly 2013-2018` downloads and unpacks them
(7z) and reads табл 3, 4, 8, 10 and 11 (not табл 6 and the higher tables, numbered differently before
2019). STATE_BUDGET_{REVENUE,EXPENDITURE,DEFICIT}_YTD, net lending and financial assets now start in
January 2013 (158 months); the quarterly STATE_BUDGET_*_Q in 2013Q1 (54 quarters); republican
wages/capital/pensions from 2013, local economic-classification lines from late 2014, oil export
duties, property and land tax from 2013. Checked: January-June 2017 revenue 5 010 193.2 as printed;
January-December 2016-2018 equal the annual reports; revenue − expenditure − net lending − financial
assets = deficit in all 70 months 2013-2018. 2008-2012 are PDF (number columns not separable from the
text layer) and are not read.

**December.** The «на 1 января» editions carry January-December but their табл 3 has annual columns
only, and the period was read from табл 3 alone: every December was missing. The period now comes from
any table of the edition, and the January-December column is the year's report column. Where that
edition is not online (2025) the annual report stands in. December now equals the annual report in
every year 2016-2025 (2020 expenditure: the report was later revised by 2.8 bn).

**Gaps.** Rows padded with empty cells (2019-2021 editions) and the class code in another column hid
the economic-classification lines and customs duties; a Kazakh-titled edition (May 2023) was not found
by the title search; the September 2022 - May 2024 editions print subsidies as specific 311 only (equal
to 310 in all 128 table-editions that print both). Republican/local wages, capital, pensions and
subsidies went from 50-71 to 86 months 2019-2026, customs duties from 62 to 87. Still missing, because
the editions are not online: April 2020, December 2025 (except табл 3 lines), April 2026; state
subsidies (табл 6) 2022-09 … 2024-05, where the table printed no subsidies line (source_issues).

**Non-oil deficit.** Minfin prints it from April 2022. In every printed month it equals deficit −
transfers from the National Fund − export duty on crude oil (44 months, to 1 mln KZT), so
STATE_NON_OIL_DEFICIT_YTD now starts in January 2018 by that identity. The annual
STATE_NON_OIL_DEFICIT for 2019-2021 was the financing row copied into the non-oil line by Minfin
(+1.29, +2.81, +2.53 trn); replaced by the identity (−5.51, −8.16, −8.06 trn; source_issues).

Tests: `tests/test_history_extensions.py` (15).

## 2026-09-27 — seven gaps for policy analysis: quasi-fiscal lending, expectations, import prices, NEER, wages, regional budgets, budget 2011-2018

**Why.** The user listed seven things missing for the SVAR and pass-through work (table «Чего нет /
Зачем нужно / Где взять»). All seven are now in the pipeline, 22 new item-level datasets.

**1. Quasi-fiscal lending.** LOANS_BY_CREDITOR_TYPE (NBK formId=445): loans by creditor —
banks, «other public sector» (the development institutions), microfinance, mortgage companies —
× currency × borrower, quarterly 2022-01…2023-07, monthly since. Other-public-sector lending to
business: 1 486 bn KZT (2022-01) → 4 485 bn (2026-08), 12.4% → 18.8% of business loans (banks +
OPS). NATIONAL_FUND_DOMESTIC_OPERATIONS (470): the National Fund's Kazakh bonds (3 378 bn at face)
and equities, FX sales, transfers, monthly from 2024-02. NBK_MONETARY_SURVEY (50): the NBK balance
sheet by line — the API now gives a mnemonic with each row code, and the identities (1 = 1.1 + 1.2 +
1.3, 3 = 1 + 2 …) hold, so it is connected (sources.yaml had declined it for lack of labels);
2.4 = claims on non-bank financial institutions, 5.2 trn. DAMU_SUBSIDISED_LOANS_ANNUAL / _MONTHLY:
sums of the ~120 000 project rows of Damu's monthly subsidy report (region × programme × ОКЭД section
× business size, by approval year since 2010, by month since 2024); region totals equal the file's
summary sheet. Approved loans: 1 186 bn (2020), 1 583 (2021), ~1 000 a year 2022-2024, 366 (2025),
26 (Jan-Aug 2026). DEVELOPMENT_INSTITUTIONS_BALANCE_SHEETS: balance-sheet lines of every IFRS
statement Baiterek (consolidated), DBK, the Kazakhstan Sustainability Fund and the Agrarian Credit
Corporation filed on KASE (fetchers/kase_ifrs.py; 104 xlsx; only columns with assets = liabilities +
equity are kept; header typos resolved by the statement's own date). Baiterek: assets 4 719 bn
(2018) → 19 048 (2025), loans to customers 2 399 → 8 033, finance leases 275 → 2 355, bonds issued
1 440 → 7 500.

**2. Budget 2011-2018** (checkpoint commit of this branch). STATE_TRANSFERS_RECEIVED_YTD (the
bulletin's «Поступления трансфертов» row, equal to the NF transfers in every overlapping month) lets
the non-oil deficit identity run before 2018: STATE_NON_OIL_DEFICIT_YTD from 2013-01 (plus four
2011-2012 months found in xls), annual non-oil deficit from 2013; STATE_BUDGET_*_Q from 2010Q1 using
the quarterly columns the bulletins print (the year carried across merged header cells). 2011-2012
monthly editions are PDF only. Still missing: 2020-01, 2020-04, 2026-04 (editions not online).

**3. Expectations.** INFLATION_EXPECTATIONS_SURVEY: the NBK household survey workbook — every
question's answer shares since 2016-01 (≈30 questions, 247 items) and the medians (perceived,
expected 12 m, expected 5 y from 2025). The long-standing February 2022 outlier (9.6) is explained:
the workbook's Q6 shares for that month are a copy of Q5's — the only such copy in 2016-2026
(source_issues updated, new entry inflation_expectations_survey_2022_02_q6). PROFESSIONAL_FORECASTS_SURVEY:
the analysts' survey chronology since 2022-08, medians by round and target year (Aug 2026: CPI Dec/Dec
2026 10.0, 2027 8.5; base rate 2026 16.0; CPI in 5 years 5.3; neutral rate 9.0). By sector (14 ОКЭД
slots, quarterly since 2005/2016): finished-goods price expectations and actuals, raw-material and
import-price expectations, demand expectations, and PRICE_FACTORS_BY_SECTOR (formId=384, share of
firms citing demand, raw materials, wages, exchange rate … since 2020-Q2). «Other industries» of
forms 362-366/384 is the N.R.S slot of the others.

**4. Import prices.** IMPORT_PRICE_INDEX_BY_HS_SECTION / _EAEU_ / _NON_EAEU_ (Taldau 19073959/60/61):
the 21 HS sections, month vs December of the previous year, 2020-01 on; IMPORT_PRICE_INDEX_YOY_BY_HS_SECTION
bridges 2016-2019 (year on year). July 2026 vs December 2025: all imports 97.2 (EAEU 98.4, rest 96.7);
footwear (XII) 98.0, textiles (XI) 98.8, cars (XVII) 97.3.

**5. Import-weighted NEER.** EXCHANGE_RATES_OFFICIAL_MONTHLY: monthly means of 18 NBK official rates
since 2010, one request per currency (a joint report shifts columns when a currency is missing),
rates printed below 1 KZT dropped (UZS, BYR before 2014), the Belarusian rouble restated for its
2016 redenomination. IMPORTS_BY_PARTNER_COMTRADE: imports by partner, consumer goods (BEC 112, 122,
522, 61, 62, 63) and all goods, 2010-2025. NEER_IMPORT_WEIGHTED: geometric chain with the previous
year's shares (euro members from adoption, dollarised partners to USD, 88-92% of imports covered),
2020 = 100, up = appreciation; NEER_CONSUMER and NEER_TOTAL; weights in NEER_IMPORT_WEIGHTS (2026:
RUB 39.3%, CNY 21.7%, EUR 16.9%, TRY 4.7%). Monthly log changes correlate 0.81 with the NBK NEER.

**6-7. Regional budgets, wage bill.** REGIONAL_BUDGETS_YTD: bulletin tables 12, 12.1-12.20 and 18
for every edition since 2013 (160 months to 2026-07; not online: 2020-04, 2025-12, 2026-04) —
revenues (PIT, social tax, transfers), spending by the 15 functional groups, net lending, balance,
subventions and withdrawals by region, January to the month. The edition's period is its latest
«январь-… отчет» header (some sheets print last year's months first), December editions read the
year's report column, «на 1 января 2023» = January-December 2022. Regions add up to table 12 within
0.5% in every complete edition; three source problems registered (source_issues): Shymkent's February
2020 sheet repeats January; table 12 of February/March 2021 is about half its regions; Abai, Zhetisu
and Ulytau are printed only from the August 2024 edition (2022-09…2024-07 miss them). Subventions
Jan-Jul 2026: 3 246.1 bn, Turkestan 656.4; withdrawal from Almaty city 319.3. SOCIAL_CONTRIBUTIONS_BY_REGION: ГФСС form 5-СО, social contributions
and insured participants by region, monthly since 2016 (Aug 2026: 85.1 bn KZT, 5.254 mn persons;
the rate rose from 3.5% to 5% in 2025 — a level break); seven months have no monthly file
(2016-06, 2016-12, 2022-01…05). PENSION_FUND_FLOWS_YTD (NBK formId=25, since 2023): mandatory
contributions 2 659 bn in 2025, 1 866 bn in Jan-Aug 2026.

**Plumbing.** New fetchers nbk_dims.fetch_classified (any NBK form classified by text fields, with
sum checks), damu, kase_ifrs, nbk_expectations, nbk_fx, comtrade, neer_import (derived), gfss,
minfin_regions; taldau `term_codes` and first-of-month dates for monthly Taldau series;
regions.csv learnt «Абайская», «Жетысуская», «Улытауская»; `backfill_minfin_bulletins.py --dims`;
LFS for data/raw/damu and data/raw/kase xlsx. Slow sources refresh weekly (refresh_days).

Tests: `tests/test_policy_gaps.py` (33); full suite 608 passed.

## 2026-09-27 — history back to 1991 and 1990s peers: GDP, population, WDI from 1960, IMF WEO for all economies, CPI weights, discrete quarterly GDP (user: «Чего в пайплайне нет …», «Что ещё не хватает …»)

**GDP from 1991.** The early sheets of BNS tables 4439-4441 («1990-1997 (ОКОНХ)», «1998-2006 (ОКЭД ГК РК 03-2003)»,
«2007-2009 (ОКЭД ГК РК 03-2007)») are read as GDP_VOLUME_INDEX_AGGREGATES, GDP_DEFLATOR_AGGREGATES and
GDP_PRODUCTION_AGGREGATES (dictionary `gdp_production_aggregates`). `gaps_filled_from` extends GDP_REAL and
GDP_DEFLATOR to 1991 and GDP_INCOME_METHOD to 1993, only while the two sources agree on every shared year
(2000-2009). Real GDP, % of the previous year: 1991 89.0, 1992 94.7, 1993 90.8; deflator 1991 201.5, 1992
1 497.5; nominal GDP 1993 29 423.1 mln KZT. This closes the 1991-1992 gap of the IMF series (from 1993).

**Population from 1991.** POPULATION_AVG_BY_REGION now reads both sheets of table 6576 (1991-2008, 2009-2025);
new POPULATION_BOY_BY_REGION (table 6584, 1 January stocks, dated YYYY-01-01 via `as_at_start_of_year`) and the
derived scalar POPULATION_BOY_BNS. POPULATION_BNS from 1991 (16 404 966.5). Source issues: the 2008 average is the
post-census 1 January 2009 stock (population_avg_2008); the stocks jump by +204 869 at 2009 and +380 751 at 2022
(census steps, not backcast).

**Peers.** WDI panels from 1960 (GDP in USD, constant USD, population) plus GDP growth, CPI inflation, deflator
inflation, GDP per capita PPP, the official exchange rate and net migration for every economy. IMF_WEO_WORLD: the
WEO for 197 countries 1980-2024 (growth, inflation, GDP in USD and PPP per capita, population, current account,
debt, unemployment; outturns only — years from each country's COUNTRY_UPDATE_DATE on are dropped; group codes
dropped).

**CPI weights before 2020.** CPI_WEIGHTS: the 12 COICOP divisions 2005-2019 as BNS reports them to the IMF
(IMF.STA/CPI WGT_PT; 2005 CP01 43.061, 2019 36.976; CP01+CP02 equals BNS's published food share, and the weights
reproduce the year-to-date CPI within 0.02-0.07 points), the 2022 scheme of the BNS brochure, and food / non-food
/ services shares for 2014-2026 (data/reference/bns_cpi_weights.csv). CPI_WEIGHTS_ESTIMATED 2020-2026: division
weights recovered from BNS's contributions to year-to-date CPI (2022 check: CP01 38.74 against 38.75).

**Real GDP for 2026 Q2.** GVA_VOLUME_INDEX_BY_SECTION_DISCRETE derives discrete quarters from the year-to-date
tables: GDP 105.2 in 2026 Q2 (manufacturing 111.1, construction 115.5). Its basis differs from the quarterly
accounts (2025 Q2: 107.0 against 109.0 in QNA), so it is not spliced into QNA_*; BNS's own Q2 is due 28.10.2026.

## 2026-09-27 — X-13ARIMA-SEATS replaces STL for seasonal adjustment

model_data/ and the seasonal-decomposition report now use X-13ARIMA-SEATS, US Census Bureau v1.1 build 62
(the official Linux ASCII build, vendored in tools/x13as/ via git LFS, sha256 72e4735d…; downloaded and
checked on demand when absent), driven by a new scripts/lib/x13.py with a hand-written spec: automatic
ARIMA (automdl), automatic AO/LS/TC outliers, log-vs-level by AICC (or forced by the spec), X-11
decomposition (SEATS optional), and a Kazakhstan calendar — working days under the holiday law (weekend
holidays moved to the next working day, Kurban Ait and Orthodox Christmas not moved, holiday list by year:
Nauryz 21-23 March from 2010, 7 May from 2013, 17 Dec and 1 Dec until 2021, 25 Oct 1995-2008 and from 2022)
plus a Kurban Ait regressor (dates 1990-2035, Kazakhstan observance) — kept only when AICC prefers it.
STL (robust) remains an explicit option and the fallback when no binary is available, recorded in each
variable card. Check: our X-13 on BNS's unadjusted real GDP reproduces BNS's own X13/JDemetra+ adjusted q/q
growth 2010-Q2..2026-Q1 with correlation 0.999 and RMSE 0.13 pp (STL: 0.907 and 1.19 pp). Against STL on the
24 variables we adjust, SA growth correlates 0.91 at the median (0.55 m0, 0.59 tax receipts, 0.67 imports:
hyperinflation-era outliers, the 2022-01 tax break, and a working-day effect in imports with t = 7.3). PPI
shows no identifiable seasonality (M7 2.11, Q 1.02). VARIABLES.md now lists model, calendar effects,
outliers and M7/Q per variable. Seasonal strength in analysis/reports/seasonal_decomposition_2026-09-28.md:
GDP_NOMINAL 0.996, IMPORTS 0.877, EXPORTS 0.463, CPI 0.131 (STL: 0.985, 0.688, 0.204, 0.174).

## 2026-09-27 — utility tariff decisions and CPI tariff jumps (TARIFF_DECISIONS, TARIFF_CHANGE_MONTHS)

**TARIFF_DECISIONS** (new, `scripts/fetchers/krem_tariffs.py`, agency `krem`) is an event dataset of
utility-tariff decisions for inflation modelling: one record per decision and service, dated by the month the
decision takes effect; item_code REGION.SERVICE.KIND.SOURCE_ID. (1) КРЕМ and its regional departments publish
into one gov.kz project, «krem»; the tariff orders are read from their titles (the files are scans): heat,
water, sewerage, electricity transmission and supply, gas distribution, transport and storage; value NaN; the
effective date is stated, or estimated as the month after the order date (or after publication for
Карагандинская and Шымкент). (2) КРЕМ press releases (gov.kz news; the endpoint needs a cookie ticket from
/api/v1/public/_/c/k6) give the stated % change, e.g. ГКП «Семей Водоканал» water −11.78% from 2026-04.
(3) Ministry of Energy electricity generation caps (order 514, order 508-н/қ and amendments, old.adilet.zan.kz):
mean % change across producer groups, e.g. +16.34% from 2023-06 and +26.33% from 2025-02. (4) Wholesale gas caps
by region 2015-2027, e.g. Almaty city 29 873 → 39 044 KZT/1000 m3 from 2025-07 (+30.7%); the 2027-07 period is
marked forecast. Coverage is uneven: departments that put order dates in titles dominate (Карагандинская,
Костанайская), and Атырауская, ВКО, СКО, Туркестанская and Павлодарская are sparse (their order files need OCR).

**TARIFF_CHANGE_MONTHS** (new, derived, `scripts/fetchers/tariff_jumps.py`) lists the months from 2004 on in
which a national CPI utility item (electricity, hot and cold water, heating, sewerage, network gas, LPG,
garbage; BNS slugs chained across the re-bases) moved by at least 3% m/m, or by at least 1.5% with a robust
z-score of at least 5: e.g. ELECTRICITY 2023-08 +6.7, HEATING 2023-11 +16.1, NETWORK_GAS 2025-08 +24.1. It dates
when the CPI registered a change, not when it was decided; national only.

## 2026-09-27 — the quasi-fiscal block before 2022: budget lending by recipient, holdings' balance sheets, NBK surveys from 1997

**RB_QUASIFISCAL_YTD** (new, `fetchers/minfin_quasifiscal.py`): budget loans (LOAN) and acquisitions of
financial assets (EQUITY) of the republican budget from the Statistical Bulletin «табл 8 (расх)», January to
the month, 2013-01 … 2026-07 (2020-04 and 2026-04 not online; 2025-12 from the untitled gov.kz document 964016).
The recipient is read from the programme label, not the codes: the first entity named is the direct
counterparty, the last one before «через» the final recipient. Items: totals; SEC.DI (development institutions
and holdings); 18 final recipients (DBK, IDF, Damu, ACC, Otbasy, Samruk-Kazyna, KTZ, the Problem Loans Fund …);
six families; the three holdings as direct counterparties; the non-quasi-fiscal rest, so the parts add up.
Checks: programmes = section header in every edition; headers = табл 7 (except its errors of 2021-02/03);
LOAN.DI = табл 10 specifics 513+519. Loans to development institutions, bn KZT: 60.0 (2013), 58.9, 68.9,
182.5, 194.1, 146.5, 246.5, 245.2, 284.7, 577.3 (2022, of which IDF 361.7), 410.3 (2023, Samruk 162.6), 274.0,
235.5 (2025). Equity: 433.1 bn in 2014 (Problem Loans Fund 250.0). Not covered: current transfers booked as
spending (2 092.9 bn to the Problem Loans Fund in 2017, Damu subsidies) and bond purchases by the National Fund,
the NBK or UAPF.

**DEVELOPMENT_INSTITUTIONS_BALANCE_SHEETS** extended (`fetchers/kase_ifrs.py`): FPKR, the Problem Loans Fund
(consolidated, 2017-12 … 2021-06, left on the KASE server after its bonds were annulled; equity -716.3 bn and
the reserve for conditional distribution -3 645.1 bn at 2019-12-31), KZAG (KazAgro consolidated, 2012-12 …
2020-09), SKKZ (Samruk-Kazyna consolidated, from 2021-12) and SKKZ_SEP (its separate Minfin Form 1, 2012-12 …
2016-03); KASE fin-data key indicators BTRK.FD_* (from 2015-12) and SKKZ.FD_* (from 2006-12). Discovery moved to
the KASE documents API; .xls statements are read (BRKZ from 2012-12). Docstring corrected: KFUS is the
Kazakhstan Sustainability Fund (2017), not the Problem Loans Fund. Fixed: BTRK.GOV_SUBSIDIES had taken the
asset «субсидии к получению» at 2020-12-31 and 2021-09-30. Aggregation: BTRK + KZAG (to 2020) + FPKR + KFUS
(+ SKKZ_SEP); never add a subsidiary to its parent.

**NBK surveys from 1997** (`fetchers/nbk_records.py`, the JSON «records» behind the NBK monetary-statistics
pages): NBK_SURVEY_HISTORY (CB), BANKS_SURVEY_HISTORY (ODC), BANKING_SYSTEM_SURVEY_HISTORY (BS) monthly from
1998, OFC_SURVEY and FINANCIAL_SECTOR_SURVEY quarterly from 2015. Stocks are dated the first day of the next
period, as form 50 (the year-month of `reporting_date` is the month-end). Enforced: the survey identities,
BS = CB + ODC for claims on NBFIs and the rest of the economy from 2002-11, CB = form 50 on the 44 common dates,
OFC = form 26. Quasi-fiscal lines: NBK claims on NBFIs (KSF, Problem Loans Fund, mostly equity) 146.2 bn at
end-2011, 1 230.1 bn (end-2017), 3 044.0 (end-2019), 5 317.6 (end-2021), 5 137.7 (end-2026-08); banks' claims on
public nonfinancial organisations; OFC claims on them (DBK among the OFCs). **BANKS_GOV_HOLDING_BORROWINGS**
(`fetchers/nbk_balance_groups.py`): banks' borrowings from the government, local executive bodies and the
national managing holding (account group 2030), IFIs (2040) and other banks (2050), monthly from 2010 (G2030
58.4 bn at 2011-01-01, 399.8 at 2015-01-01, 712.0 at 2026-08-01; break 2023-02 when Damu joined group 2030).
Source issues registered: the misdated 2003-04 banks' record, six NBK identity errors, the unpublished NDA line
from 2009, the 2015-06 step in NBK claims on the rest of the economy, the 2023-02 Damu reclassification.

## 2026-09-28 — official exchange rates back to the tenge's introduction (November 1993)

EXCHANGE_RATE, EXCHANGE_RATE_RUB (from 1993-11-18), EXCHANGE_RATE_CNY (from 1996-02-05) and
EXCHANGE_RATE_EUR (from 1999-01-04) now reach back before the NBK daily report, whose first usable
day is 1999-11-17. The history comes from the NBK archive workbook «Архив официальных курсов валют
с 1993 по 1999» (nationalbank.kz/file/download/22756): effective-date rows turned into the rate in
force on each weekday, the series' existing definition. The archive is re-read on every run and must
equal the report on all 33 weekdays of 1999-11-17..12-31 (0 differences), or the fetcher stops. USD at
year-end: 6.31 (1993), 54.26, 63.95, 73.30, 75.55, 83.80 (1998), 138.20 (1999), all equal to IMF IFS;
the float of April 1999 runs 87.50 (2 April) -> 100.00 (5 April) -> 118.00 (7 April). Monthly means
match the NBK's published averages within 0.05 except 1994-01, 1997-01 and 1998-01. The rouble is in
new (post-1998) roubles throughout: the archive's quote per 1000 roubles before 1998 is one new rouble
(13.00 on both sides of 1 January 1998). No euro before 1999: the archive's ECU and Deutsche mark are
not spliced. Rates were set once or twice a week before April 1999, so the early daily series is a
step function. Tests: tests/test_fx_history.py (14).

## 2026-09-28 — CIS Stat: the CIS countries since 1991, Kazakhstan migration before 2000

New fetcher `scripts/fetchers/cisstat.py` (agency `cisstat`) reads the JSON service of the CIS Stat
database «Статистика СНГ» (new.cisstat.org/consstat, no key) into four item-level datasets whose
`region` is the reporting country's ISO3 code: CIS_GDP_VOLUME_INDEX (fact 714662, real GDP % of the
previous year, 11 countries 1991-2025), CIS_CPI (fact 43370, December on December and annual average
as separate items, by consumer group), CIS_POPULATION (facts 44176/44177, 1 January and annual
average) and CIS_MIGRATION (facts 4650866/4679599 by flow, 44243/44245 by partner country from 2016;
net = arrivals - departures). Kazakhstan's GDP index equals BNS GDP_REAL in every year 1991-2025
(1991 89.0, 1992 94.7, 1993 90.8) and its Dec/Dec CPI equals BNS CPI_YOY in 2011-2025; the 1990s CPI
(1994: average 1 877%, Dec/Dec 1 158%) differs from the IMF's (1 402% / 855%). MIGRATION_ARRIVALS and
MIGRATION_DEPARTURES now start in 1991 (1994: 70 389 arrived, 477 068 left) via `gaps_filled_from`
CIS_MIGRATION; the sources agree on 2000-2025 except 2008 (CIS Stat 46 404 / 45 287, BNS 46 113 /
44 813), which `fill_gaps` now skips through the new `known_differences` key, keeping BNS's value.
Hard checks: header columns, every country/flow/group/base/sex/area label mapped, numeric values, no
conflicting duplicates, Kazakhstan present 1991-1999, and for Kazakhstan the partner sums and the two
migration facts' totals. Tests: tests/test_cisstat.py (19, no network).

## 2026-09-28 — national CPI back to 1991

CPI and CPI_YTD now start in January 1991 and CPI_YOY in January 1994 (BNS published no
year-on-year index for 1991-1993); before, all three started with Taldau in January 2011. The
240 (204) earlier months are BNS's own printed figures from three stat.gov.kz sources — «Цены в
Казахстане за 1991-2021 годы» (element 17216, docx: Dec/Dec 1991-2021, m/m 1992-2021), «Цены в
Казахстане в 1991-2000 гг.» (element 21933, pdf: m/m, since December and, from 1994, y/y) and the
140 monthly editions of publication 166775 (May 1999 – December 2010) — loaded by
`scripts/load_cpi_history.py` into `data/reference/bns_cpi_history.csv`. Every month two sources
print is the same number in both (228 of 240 m/m months have a second source; the editions equal
CPI_DETAIL on all 234 values 2004-07…2010-12), and the three measures satisfy the CPI identities
within rounding (chain of m/m = since-December; y/y = product of 12 m/m = ytd(t)/ytd(t−12)·Dec/Dec).
One printed inconsistency is kept as published: February 1993 m/m 131.9 where the since-December
figures imply 131.7. The fetcher prepends only months before 2011 and stops if the file differs
from Taldau on any of the 132 m/m months and 11 Decembers of 2011-2021 the docx repeats (all equal).
December/December: 1991 247.1, 1992 3060.8, 1993 2265.0, 1994 1258.3, 1995 160.3, 1996 128.7,
1997 111.2, 1998 101.9, 1999 117.8, 2000 109.8. Tests: tests/test_cpi_history.py (25).
The analysis and model layers keep their CPI sample from 2011: `model_data/spec.yaml` `cpi` has
`from: "2011-01-01"` (now applied before chaining, so the level is still 100 in 2011-01), and the CPI
targets of `scripts/analysis/seasonal_targets.py` / `forecast_targets.py` carry `sample_start`
(new, passed to `timeseries.prepare_level`). Move the start to 1996 only after checking the X-13
diagnostics; 1991-1995 hold m/m values up to 312.3 (source issue cpi_1991_1995_hyperinflation).
model_data's `usdkzt` now starts in 1994-01 (the NBK archive); 1999-11 is 139.63, the NBK's
published average, instead of 138.80 from the report's last 11 weekdays.

## 2026-09-28 — CPI groups (food, non-food, paid services) back to 1991 (user: «Сделай все три пункта»)

CPI_FOOD, CPI_NONFOOD and CPI_SERVICES (m/m) now start in January 1991 and their _YOY in January
1994, like the headline; before, all six started with Taldau in January 2011. The 240 (204) earlier
months come from the same three BNS publications, now read per group: «Цены в Казахстане за
1991-2021 годы» (element 17216, docx: tables 1.4-1.6 m/m 1992-2021 and the group columns of table
1.1 Dec/Dec), «Цены в Казахстане в 1991-2000 гг.» (element 21933, pdf columns 2-4) and the 140
monthly editions of publication 166775 (1999-05…2010-12; html rows «Продукты питания, напитки и
табачные изделия» / «Непродовольственные товары» / «Платные услуги», xls through the CPI_DETAIL
parser). `data/reference/bns_cpi_history.csv` gained an `item` column (TOTAL for the 838 headline
rows, values unchanged; 3 352 rows). Per group 228 of 240 m/m months have a second source, and
every month two sources print agrees except food June 2004: the docx and the edition's own m/m
table print 100.0, its summary row «Продукты питания, напитки и табачные изделия» 99.9 — kept as
100.0 and listed in the loader's PRINTED_DIFFERENCES (source issue cpi_food_2004_06_mom_two_prints).
The xls editions equal CPI_DETAIL on all 936 values 2004-07…2010-12. The identities hold within
rounding for every group with no slack (chain of m/m vs since-December at most 0.38 pp from 1995,
y/y vs 12 m/m at most 0.40 pp from 1996). The fetcher stops if the file differs from Taldau on any
of the 132 m/m months or 11 Decembers of 2011-2021 per group (all equal); no stored 2011-2026 value
changed. December/December, food: 1992 2108.3, 1993 2297.1, 1994 1155.7, 1995 158.7, 1999 120.6;
non-food: 1992 3897.8, 1993 1795.6, 1994 1159.9, 1995 133.5, 1999 119.8; paid services: 1992
3019.7, 1993 4143.4, 1994 2522.6, 1995 258.0, 1996 239.3, 1999 109.9. model_data keeps cpi_food /
cpi_nonfood / cpi_services from 2011 (`from: "2011-01-01"` in spec.yaml; the panels are unchanged).
CPI_UTILITIES and CPI_REGULATED_UTILITIES still start in 2011. Tests: tests/test_cpi_history.py (54).

The official quarterly accounts for 2026 Q2 (BNS, element 283161, due 28.10.2026) are picked up by the
daily update_all run; a check is scheduled for 29.10.2026 to compare them with the discrete estimate
(GVA_VOLUME_INDEX_BY_SECTION_DISCRETE: GDP 105.2) and rebuild model_data.

## 2026-09-28 — partner-currency rates back to 1993, import-weighted NEER from 1995

EXCHANGE_RATES_OFFICIAL_MONTHLY (18 currencies, KZT per one current unit, weekday means) now starts in
1993-11 instead of 2010-01. 1999-11..2009-12 come from the NBK daily report (read once in 10-year windows,
first usable day 1999-11-17, malformed October 1999 rows dropped); before the report, the NBK archive
«Архив официальных курсов валют с 1993 по 1999» (rate in force on each weekday) for the 11 currencies it
carries, equal to the report on every common weekday of 1999-11-17..12-31 for USD, EUR, CNY, RUB, GBP, CHF,
JPY and KGS (enforced). Printed figures below 1.0 are dropped in both sources, so TRY runs 1994-05..1996-02
then from 2005, UZS and BYN have 1990s fragments then start in 2014-02; KRW from 2000-05, AED 2001-07, PLN
2004-09, CZK 2009-03, EUR 1999-01, CNY 1996-02; INR, TJS and AZN still from 2011-2014. Redenominations are
listed in nbk_fx.REDENOMINATIONS and checked against the data: RUB 1998 (archive already per new rouble,
13.00 on both sides), TRY 2005 (TRL x10^6), BYN 2000 and 2016 (BYB x10^7; BYR x10^4 up to Friday 1 July 2016
inclusive -- the report's rate in force that day is still per 100 BYR, first BYN quote 2 July, step x10 162),
UZS 1994 (archive per 1000 coupons = one sum); any other step above x8 within a month stops the fetcher.
This corrects BYN 2016-07 (163.00 -> 171.00; NEER 2016-07 by -0.1, recorded in the revisions files); every
other stored month since 2010 is unchanged. USD/EUR/CNY/RUB equal the monthly means of the daily
EXCHANGE_RATE* series in every month. Monthly USD 1999-12 138.22, 2005-01 130.10, 2009-12 148.70; RUB 5.12,
4.66, 4.97; EUR 143.15, 171.38, 217.64; TRY 2005-01 96.07, 2009-12 98.70. IMPORTS_BY_PARTNER_COMTRADE now
starts in 1995 (Kazakhstan's first Comtrade year), so NEER_IMPORT_WEIGHTED starts in 1995-12 (NEER_TOTAL,
2020 = 100: 93.9; 1998-09 158.8 after the rouble crash, 1999-03 266.4, 1999-06 179.1 after the float) and
NEER_IMPORT_WEIGHTS in 1996; its monthly changes correlate 0.84 with the NBK's own NEER in 1996-2009. Before
1999 the euro-area partners have no rate (coverage 59-77%; 80-92% from 2000); CONSUMER 2000 is a partial
Comtrade conversion (36 mln USD) and is replaced by the 1999 structure; 1995-1999 CONSUMER includes passenger
cars (H0 conversion). Three archive typos (CHF 17.04.1995, 09.11.1998; KGS 09.08.1999) are kept as printed and
registered in source_issues. Tests: tests/test_fx_monthly_history.py (15).

## 2026-09-28 — weekend rows removed from the daily official USD rate (user: «Почисти записи за выходные в дневном ряде USD»)

EXCHANGE_RATE held four weekend rows (2026-08-22/23 at 456.88 and 2026-08-29/30 at 464.77, Friday's
rate repeated) written by an earlier fetcher; the fetch kept them because only the fresh report rows
were filtered to weekdays, not the stored history they were merged with. `nbk._fetch_official_rate`
now keeps weekdays only after the merge, for all four official-rate series (EUR, CNY and RUB had no
weekend rows). The August 2026 mean of the daily series moves from 463.96 to 464.55, equal to
EXCHANGE_RATES_OFFICIAL_MONTHLY USD (464.551429); model_data usdkzt 2026-08 likewise (usdkzt_yoy
-13.91 -> -13.80). Test: tests/test_fx_history.py::test_fetcher_drops_weekend_rows_already_stored.
