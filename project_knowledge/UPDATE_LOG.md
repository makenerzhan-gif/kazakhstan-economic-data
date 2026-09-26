# Update Log

Recent entries, oldest first; append new ones at the end. Entries from 2026-08-30 to 2026-09-15
are in docs/UPDATE_LOG_ARCHIVE.md in the repository (not synced into the Claude Project). When this
file grows past ~60 KB, move the oldest entries there.

## 2026-09-23 — quarterly data: fourteen year-to-date and quarterly siblings of the item-level datasets; GDP_NOMINAL derived from them

**Why.** The item-level layer read only the «YYYY год» columns of the BNS national-accounts
tables; the same xlsx files carry «1 квартал», «1 полугодие» and «9 месяцев» beside them
(as columns in 4439–4441, 4435–4437, 4452–4455 and 5926, as rows inside the region blocks
of 5927 and 5931), and the employment table 5831 carries «I–IV квартал» sub-columns under
every year. The user asked for the quarterly data.

**What.** Fourteen datasets, each the sibling of an annual one (same element, same rows,
same dictionary, id suffixed `_QUARTERLY`, `frequency: quarterly`), 44 328 rows in
`macro_dims_long.csv` (95 764 in all):

| dataset | rows | items × regions | periods |
|---|---|---|---|
| GVA_NOMINAL_BY_SECTION_QUARTERLY (4439) | 1 821 | 30 | 2010 Q1 – 2026 H1 |
| GVA_VOLUME_INDEX_BY_SECTION_QUARTERLY (4440) | 1 821 | 30 | 2010 Q1 – 2026 H1 |
| GVA_DEFLATOR_BY_SECTION_QUARTERLY (4441) | 1 821 | 30 | 2010 Q1 – 2026 H1 |
| GVA_NOMINAL_INDUSTRY_DIVISIONS_QUARTERLY (5931) | 1 961 | 37 | 2013 Q1 – 2026 Q1 |
| GDP_EXPENDITURE_NOMINAL_QUARTERLY (4435) | 1 080 | 15 | 2007 Q1 – 2026 Q1 |
| GDP_EXPENDITURE_VOLUME_INDEX_QUARTERLY (4437) | 847 | 11 | 2007 Q1 – 2026 Q1 |
| GDP_EXPENDITURE_DEFLATOR_QUARTERLY (4436) | 924 | 12 | 2007 Q1 – 2026 Q1 |
| INCOME_COMPENSATION_BY_SECTION_QUARTERLY (4453) | 1 560 | 24 | 2010 Q1 – 2026 Q1 |
| INCOME_OTHER_TAXES_BY_SECTION_QUARTERLY (4452) | 1 625 | 25 | 2010 Q1 – 2026 Q1 |
| INCOME_CFC_BY_SECTION_QUARTERLY (4454) | 1 560 | 24 | 2010 Q1 – 2026 Q1 |
| INCOME_PROFIT_BY_SECTION_QUARTERLY (4455) | 1 567 | 25 | 2010 Q1 – 2026 Q1 |
| GVA_NOMINAL_BY_REGION_SECTION_QUARTERLY (5927) | 25 256 | 25 × 22 | 2010 Q1 – 2026 Q1 |
| GRP_VOLUME_INDEX_BY_REGION_QUARTERLY (5926) | 1 099 | 1 × 22 | 2011 9 months – 2026 Q1 |
| EMPLOYED_BY_SECTION_QUARTERLY (5831) | 1 386 | 21 | 2010 Q1 – 2026 Q2 (discrete) |

Every period of the national-accounts tables is YEAR-TO-DATE (January–March, January–June,
January–September, the year); the values are stored as published, not decumulated. The
employment quarters are discrete (a labour-force-survey quarter), which the data itself
proves: its Q4 differs from the annual figure on all 336 (year, item) pairs, while in every
year-to-date dataset Q4 equals the annual sibling's value on all 10 707 (year, region, item)
pairs. Dating follows `lib/periods.py` and the scalar `GDP_NOMINAL`: the first day of the
last quarter covered (2024-07-01 for January–September 2024, 2024-10-01 for the year).
The flow tables say `cumulation: year_to_date` (the outlier check then compares own-period
contributions, as for the scalar year-to-date series) and carry the same `transformation`
text as `GDP_NOMINAL`; the indices' unit says they are year-to-date periods in % of the same
period of the previous year. 5926's year-to-date columns begin with «9 месяцев 2011 года»
(`years_from: 2011`; 2001–2010 stay annual). 450904 has annual rows only — no sibling.

Parser (`scripts/fetchers/bns_dims.py`): `period_of` reads every label shape seen in the
files («1 квартал 2010г.», «I квартал     2012 года», «1 полугодие 2026г.*», «9 месяцев
2019 года**», «9 месяц 2012г.», «2025 год7)8)», a Cyrillic І), `quarter_of` the bare
«I–IV квартал» sub-column labels (a year whose sub-columns are labelled otherwise stops the
dataset loudly); `_period_columns` / `_rec` date the period; `periods` and `years_from` are
dataset keys. `dims.validate` takes `cumulation`; `update_dims` writes the dataset's
`transformation` into every processed row and the metadata. One download and one raw copy
per file as before: the thirteen files were byte-identical to the 14/16 September copies,
so the run stored fourteen manifests and no new bytes. Validation warnings are seasonal
(agriculture's third-quarter contribution, other taxes in Q4) and one row of 4440/4441
(NET_TAXES) that is published annually only — informational, none failed.

**GDP_NOMINAL.** The scalar was fetched from the JSON cube of the same element 4439. Its 66
quarters equal the xlsx «ВВП» row × 1e6 within the table's rounding to 0.1 million KZT (only
2010 Q2 differed, by 48 795 KZT, where the cube carried unrounded tenge), so it is now the
twelfth derived scalar (`derived_from: GVA_NOMINAL_BY_SECTION_QUARTERLY[GDP] × 1e6`) — one
download instead of two, `fetch_gdp_nominal` retired, `sources.yaml` says `derived`.
`update_derived` now keeps the source dataset's `transformation` (the year-to-date text) in
the processed rows and the metadata, and scales with `Decimal`: in floats 16804418.1 × 1e6 is
16804418100000.002, and that noise had been logged as "revisions" of GDP_NOMINAL (three
quarters) and stored in ELECTRICITY_PRODUCTION (1994 and 2004 since 15 September). The
noise entries dated today were removed from the two revision logs (they were artefacts of
the multiplication, not of the source); the genuine 2010 Q2 entry stays. ELECTRICITY_PRODUCTION
2014 keeps its fractional value (94 643 242 900.00002) because the xlsx cell itself holds
94643.24290000001. `macro_long.csv`/`macro_wide.csv` and `project_knowledge/` rebuilt.

Tests 311 → 338 (`tests/test_dims_quarterly.py`: every label shape, the three layouts under
`periods`, `years_from`, the structural stop on mislabelled sub-columns, the year-to-date
outlier check, and that every quarterly dataset mirrors its annual sibling's configuration).

**Left out.** Discrete quarters for the year-to-date flows (a decumulation transformation,
to be its own derived layer if ever needed, never a silent change of these); 450904 (no
quarterly rows); the model has no quarterly mappings — nothing in `config/model_map.yaml`
changed and the daily run's model check is unaffected.

## 2026-09-23 — discrete quarters: the quarterly national accounts (19 QNA_* datasets), and a second vintage of the 2010–2022 history

**Why.** The year-to-date siblings added earlier today are what the dynamic tables offer;
the user asked for discrete quarters («Найди дискретные кварталы», then «1 вариант» — all
four tables in full).

**Where they are.** Not in the dynamic tables 4439–4441 / 4435–4437 / 4452–4455 / 5926 /
5927 / 5931 and not in Taldau (index 2709379 offers «Год» and «Квартал с накоплением» only —
checked live): the national-accounts «Динамические таблицы» page has a group headed
«Экспериментальная оценка Валового внутреннего продукта» with four workbooks — 283162 «ВВП
методом производства (на квартальной основе)», 283161 «ВВП методом конечного использования
на квартальной основе с сезонной корректировкой», 283160 «ВВП методом доходов (на
квартальной основе)», 471384 «Валовой региональный продукт на квартальной основе». Their
annotation: quarterly national accounts compiled with IMF technical assistance, discrete
quarters benchmarked to the annual accounts (XLPBM, Denton / Cholette-Dagum), seasonal
adjustment by X13-ARIMA-SEATS in JDemetra+ 2.2.4, and — «параллельно с внедрением КНС» — a
recalculation of the annual national accounts 2010–2023 to SNA 2008.

**What is stored.** 19 datasets, 37 341 rows, layout `year_quarters` (a year row over four
quarter sub-columns; `cumulative: true` reads «I квартал | I полугодие | 9 месяцев | год»
or «Январь - Март … год»; `region_col` for the regional blocks; `components` + `component`
for the income account, whose activity rows have no numbers and whose component rows repeat
under each activity):

| element | datasets | rows | periods |
|---|---|---|---|
| 283162 production | QNA_GVA_BY_SECTION, _CONSTANT_2010, _VOLUME_INDEX_BY_SECTION, _VOLUME_INDEX_BY_SECTION_YTD, _DEFLATOR_BY_SECTION_YTD, _SA, _SA_CONSTANT_2010 (26 items) | 1 690 / 1 690 / 1 586 / 1 586 / 1 586 / 1 690 / 1 690 | 2010 Q1 (indices 2011 Q1) – 2026 Q1 |
| 283161 expenditure | QNA_GDP_EXPENDITURE, _CONSTANT_2010, _VOLUME_INDEX, _VOLUME_INDEX_YTD, _DEFLATOR_YTD, _SA, _SA_CONSTANT_2010 (13–16 items) | 1 040 / 910 / 854 / 854 / 854 / 910 / 845 | 2010 Q1 – 2026 Q1 |
| 283160 income | QNA_GDP_INCOME (4 items); QNA_INCOME_COMPENSATION / _OTHER_NET_TAXES / _GROSS_PROFIT _BY_SECTION (24 items each) | 260; 3 × 1 560 | 2010 Q1 – 2026 Q1 |
| 471384 regions | QNA_GVA_BY_REGION_SECTION (24 items × 21 regions) | 14 616 | 2019 Q1 – 2026 Q1 |

Not stored, by the de-duplication rule: the cumulative twins of the current- and
constant-price sheets (283162 1.1/2.1, 283161 1.1/2.1, 283160 1.1/2.1, 471384's second
sheet) — proven to be the running sums of the discrete quarters (283161: 1 040 + 910
points, 283160: 260, 283162: 1 690 constant-price points, all equal) — and the ВДС rows of
the income account, equal to QNA_GVA_BY_SECTION on 1 491 of 1 495 common points (the four
exceptions, I quarter 2026: A/GOODS 6 034 lower, L/SERVICES 311 169 million KZT higher in
the income account — recorded in the datasets' notes). The cumulative twins are nonetheless
re-read on every run (`cumulative_check`): any point that is not the running sum of the
stored quarters is a warning, the discrete value is kept. Today that warning fires once,
and it is real: in 471384 the four quarters of 2025 sum above the file's own «год 2025» —
which equals table 5927 — in five regions (AKM +2.2 %, AKT +20 %, ATY +15 %, ZHM +16 %, ZKO
+16 %; IV quarter 2025 carries the whole difference; the national total agrees). Two
misspelt activity labels in 283160 («Оптования и розничная торговля», «Проффесиональная»)
are mapped by `label_overrides`; the cumulative income twin abbreviates «I кв.» and puts
numbers on the «Производство услуг» group row — both handled. The four files are 1.3 MB
together, one raw copy each (the datasets of one file share it).

**Two vintages — the finding that matters for the model.** Q1+Q2+Q3+Q4 of the discrete
tables equal the dynamic annual tables only for 2023–2025 (283162 vs 4439: 26/26 sections
equal in each of 2023, 2024, 2025, 0/26 in 2010–2016, 5–8/26 in 2017–2022; 283161 vs 4435
and 471384 vs 5927 likewise). For 2010–2022 the quarterly tables carry the SNA-2008
recalculation: GDP 2010 +9.4 %, 2011 +6.5 %, 2012 +5.9 %, 2013 +3.4 %, 2014 +3.1 %, 2015
+1.6 %, 2016 +0.1 %, 2017 −2.6 %, 2018 −2.9 %, 2019 −2.9 %, 2020 −2.0 %, 2021 −1.6 %, 2022
−1.5 % against 4439; the volume index differs too (2020: 98.5 vs 97.5). The dynamic tables
and Taldau (2709379, checked live 2026-09-23: GDP 2010 still 21 815 517 million KZT) have not
been moved to the revised series. Every QNA_* dataset carries this in `vintage` (metadata
`methodology`) and a `transformation` that names the vintage; the annual datasets, the
year-to-date siblings and `config/model_map.yaml` are untouched — the GDP model's 2010–2022
history stays on the published dynamic-table vintage until its author decides otherwise.

Also: `dims.normalise_region_label` folds «город Астана» to the dictionary's «г. Астана»;
`dictionaries/income_components.csv` (4 codes) is new; `expenditure_items.csv` tells GDP by
production (`GDP_PRODUCTION`) from GDP. Tests 338 → 349 (`tests/test_qna.py`,
`tests/test_qna_cumulative_check.py`).

**Left out.** The cumulative twins as data (running sums); the ВДС component of the income
account (four points differ, noted); any use in the model.

## 2026-09-23 — the second vintage in the model: sheet «Факт_КНС» (1 662 values from the QNA_* datasets), option Б

**Why.** The comparison of the two vintages (report https://claude.ai/artifact/Ay5rFQ8Mmc2etvmYy5qefq:
GDP 2010 +9.4 %, 2017–2022 −1.5…−2.9 %, transport −21 % in 2022, a 2022/2023 seam inside table
4439 that breaks nominal × ИФО × deflator = nominal by +1.5 % for GDP and +27 % for transport)
ended with three options; the author chose Б — load the quarterly national accounts' annual
values into the model as a separate block, leave the history sheets and the published vintage
untouched.

**What.** A new sheet «Факт_КНС» (after «Контроль») with five tables, row 1 carrying the years
2010–2025 in C..R as every mapped sheet does: (1) ВДС by section in current prices — the sum of
the four discrete quarters of QNA_GVA_BY_SECTION (26 items, 416 values); (2) ИФО ВДС — the «год»
value of QNA_GVA_VOLUME_INDEX_BY_SECTION_YTD (2011–2025, 390); (3) deflators — likewise (390);
(4) GDP by expenditure, sum of quarters of QNA_GDP_EXPENDITURE (16 components, 256); (5) its
volume index, «год» value (14 components, 210). Codes in column A follow «Факт_БНС» (ВДС, ЧН,
ВВП) plus ПТ/ПУ/ПР for goods/services/industry and short codes for the expenditure components;
blue font marks pipeline data; the header rows 2–4 state the source files (283162 of
17.08.2026, 283161 of 28.07.2026), the vintage difference and that no formula reads the sheet.
Written with scripts/lib/excel_apply.ps1 (39 ops, 11 s) from scratchpad/quarterly/plan_qna.py;
«Журнал_правок» gained 7 rows (1 495 → 1 502). Every other sheet is unchanged cell for cell
(formulas and cached values; «Контроль» included).

Five mappings in `config/model_map.yaml` (`fact_qna_*`, `rows_by_item`, `annual: sum` for the
flows and `annual: last` on the year-to-date index datasets, years 2010–2025 / 2011–2025) make
the sheet part of the daily contract: model_sync on the new copy reports the block as
1 662 ok / 0 diff / 0 missing; the full check is 7 407 ok, 0 diff, 3 control, 183 missing (the
three controls are formula cells that differ from today's pipeline value by more than their
tolerance, one of them in gva_deflator_sections — reported, never overwritten). model_coverage: 68 318 numbers, 5 871 from the
pipeline, 62 447 manual, 0 unaccounted. `default_file` now points at the author's renamed
folder «Модель ВВП по производству».

The revised copy replaced `…_rev_2026-09-14.xlsx` on Yandex.Disk after checking the previous
hash (b115ea6f); new SHA-256 bc2f716e…; the original 15.01.2025 file is untouched (3f5a1228…).

**Left out.** No formula of the model uses the new sheet — how the author wants the structure or
contribution calculations to read it is their call; the history sheets stay on the dynamic-table
vintage until BNS revises those tables (the daily check will show it as revisions).

## 2026-09-23 — the rest of the national-accounts page: 15 tables, 35 datasets, 84 492 rows

**Why.** The user asked whether every table on the BNS national-accounts «Динамические
таблицы» page is in the pipeline. Of 47, 20 were; 6 are derivable from those (structure
shares, regional shares, GRP per capita, GDP by income as a whole, GDP per capita in tenge);
6 are one-off or narrow publications (experimental SUT-based GDP/GRP 2024, the financial
balance-sheet pilot, creative industries, supply-use tables in previous-year prices — offered
to the МОБ project instead). The user said «Добавь» to the remaining 15.

**What.** 35 datasets, 84 492 rows, eight new sheet layouts in `scripts/fetchers/bns_dims.py`
(described in its docstring): `year_sheets` (81477 gross output by region and section, 81478
the production account by region, 2022–2025), `periods_across` with new dictionaries (286855
six annual SNA aggregates 2010–2024; 4445 the oil-and-gas / commodity sector tables — 32 items:
sector aggregates and their product lines, `dictionaries/oil_gas_sectors.csv`; 5923 GRP by
region from 1993 — 1990–1992 are in roubles and skipped — plus its year-to-date quarterly
series 2008 Q1 on; 5932 the non-observed economy's share of GDP and of GRP by region; 75044's
quasi-public GVA share and large-enterprise productivity), `year_quarters` with a cumulative
flag (4449 labour productivity by section, 4450 its index y/y and 2022 = 100, 5934's regional
index 2022 = 100), `year_blocks_items_regions_ytd` (5933/5934 productivity and its index by
region and section since 2010/2011 — 23 581 and 22 237 rows), `year_blocks_regions_items`
(5932 NOE by region and activity), `year_blocks_items_regions` (75044 quasi-public GVA by
region and section, the year read from each block's title), `year_subcolumns` (75044 GVA by
enterprise size, three datasets), `month_rows` / `year_months` / `region_blocks_months` (5941–
5943 the short-term economic indicator: monthly level, year-to-date level, volume index by
country, region and region × activity from January 2021), `sector_columns` (410224 GDP
components by institutional sector S11–S15 and total: output, intermediate consumption, GVA,
compensation, other taxes, consumption of fixed capital, net profit — items «<activity>_<sector>»,
seven datasets). New dictionaries `sna_aggregates`, `production_account`, `oil_gas_sectors`,
`kei_activities` (the indicator's «Связь» stays COMMUNICATIONS, not folded into J);
`regions.csv` learnt «Нур-Султан» (AST) and BNS's misspelt «Карагандиская». Quirks handled
loudly rather than guessed: 5933/5934's current-year block repeats «1 квартал» in all four
sub-columns (the last block may stop early); 81478's sheet «2023 год » has a trailing space
(all «YYYY год» sheets are taken); 5941 puts the year marker in column B for 2025–2026 and
column C before; 5943's column labels carry their own year («ИФО, января 2022г. к …»);
5932's third sheet has one header for all year blocks. Every dataset states in `note` what it
reads. Live run: 35/35 ok; the 15 files are 1.9 MB together, one raw copy each.
`macro_dims_long.csv`: 133 105 → 217 597 rows, 115 datasets. Tests 349 → 359
(`tests/test_na_page_layouts.py`).

**Not taken, and why.** 4450's sub-industry sheets (agriculture, ICT by division) and 5934's
«к уровню 2019» — older base; 4445 «Свод» and 75044 «Доля по КРП» — derived from the sheets
read; 469090/471272 (experimental GDP/GRP 2024 on a SUT basis — text sheets), 466862
(financial assets by sector, one year), 345748 (creative industries 2018–2023), 470989
(supply-use tables in previous-year prices, experimental — for the МОБ model, not this
pipeline). Nothing in `config/model_map.yaml` changed.

## 2026-09-23 — the unified item-level file is gzip-compressed: macro_dims_long.csv.gz (2.2 MB instead of 61 MB)

**Why.** With 115 datasets the unified item-level file reached 217 597 rows and 61 MB; GitHub
warned on the push that it exceeds the recommended 50 MB, and every daily run rewrites it. Git
LFS was rejected (a public repository's LFS quota would be consumed by a 61 MB daily rewrite);
dropping the file from the repository was the alternative, but it is the one place a reader
finds every item-level series at once.

**What.** `lib/dims.UNIFIED_PATH` is `data/unified/macro_dims_long.csv.gz`; `write_long_csv`
and `model_sync.load_unified_dims` go through `dims.open_unified`, which gzips by the file's
name and still reads a plain .csv (tests cover both). The plain file was removed from the
repository; the columns and content are unchanged (2 180 176 bytes compressed, 28× smaller).
`pandas.read_csv` and `csv` over `gzip.open` read it directly; the scalar `macro_long.csv`
(1.8 MB) stays plain. README, config comments and docstrings updated. Tests 359 → 360.

## 2026-09-23 — raw store: an LFS pointer counts as the archived copy (CI stored every BNS workbook again each day)

**Found.** The manual run 35877301328 (54 min, 545/545 ok, no data change) added 76 raw BNS
workbooks, and every scheduled run since 2026-09-16 added 58 — all byte-identical to files
already archived (`cmp` on 4439 for 22 and 23 September: identical). The workflow checks the
repository out with `lfs: false`, so in CI each archived `data/raw/bns/*.xlsx` is a 130-byte
Git LFS pointer; `raw_store.identical_twin` compared bytes, saw a "different" file and archived
the unchanged download again under a time-suffixed name. At HEAD: 790 pointer files for 88
distinct objects (597 MB of content, 702 duplicate pointers). GitHub LFS storage is
content-addressed, so the duplicates cost repository clutter and 2.3 GB of smudged copies in
a local checkout, not LFS quota.

**What.** `raw_store.holds_content` treats a file as holding the download either literally or as
an LFS pointer whose `oid sha256:` equals the download's sha256; `identical_twin` and the
same-day branch of `save_raw_bytes` use it. Revised content still lands as a new file; nothing
archived is touched. Verified on a real workbook against a simulated CI worktree (pointer
stub for the previous day → twin found, nothing written) and against the local archive.
Tests 360 → 362 (`tests/test_raw_store.py`). The 702 duplicate pointers already in the
repository are left in place; removing them is the same operation as the 2026-09-15 dedup
(a record file mapping each removed file to the file that holds its bytes) and is the
author's decision.

## 2026-09-23 — 702 duplicate raw copies removed; every manifest re-pointed (user: «Удали дубликаты»)

**What.** `scripts/dedup_raw.py` removed the 702 byte-identical BNS workbooks that the CI runs of
2026-09-16..23 had archived again (80 distinct contents, 2 326 MB of smudged copies; verified
before removal that each removed pointer's LFS oid equals the surviving file's). Record:
`data/raw/dedup_2026-09-23.json` (removed → kept, 702 entries). Nothing with distinct content
was touched; the raw tree keeps one file per content, the earliest archive of it.

**Found and fixed on the way.** The dedup of 2026-09-15 re-pointed only the manifest named after
a removed file; the manifests of the other indicators that read the same shared workbook (346883
feeds AVG_WAGE_QUARTERLY and AVG_WAGE_AGRICULTURE; 335623 the construction index and output;
5831 the employment tables …) kept naming the removed file. Today's removal would have left 732
such manifests dangling. `dedup_raw.point_manifests` now re-points every manifest in the folder
that names the removed file, and `--repair-manifests` follows the dedup records (across chains)
for manifests left dangling earlier: 732 repaired, 0 dangling among the 10 502 manifests
afterwards. `raw_file` in a manifest is written by the fetchers and read by nobody in the
pipeline, so nothing had failed — the record was simply wrong. Tests 362 → 364
(`tests/test_dedup_raw.py`).

## 2026-09-25 — independent data audit and the fixes it called for (user: «проверь все данные», «исправляй»)

**Audit.** `reports/data_audit_2026-09-25.md`: all 430 indicators and 115 item-level datasets
re-parsed from `data/raw/` with parsers written for the audit (not the pipeline's). Every value
matched its raw file; the problems were dates, gaps, labels and errors inside the sources.

**Fixed in the pipeline.**
- *NBK / ARDFM flows dated one period late.* NBK open data stamps a flow or an average with the day
  after its period (report_date 2020-04-01 = Q1 2020 of the balance of payments). New
  `date_basis: next_period_start` (with `date_basis_evidence`) on 30 indicators — the BOP lines and
  GDP ratios of form 485, OTC rates and volumes (form 41), KASE volumes (form 35), LENDING_RATE,
  PENSION_PAYMENTS, INSURANCE_PREMIUMS_*, GOV_SECURITIES_SECONDARY_NBK_NOTES, and ARDFM's
  BANK_NET_INCOME / ROA / ROE / LIQUID_ASSETS; `periods.apply_date_basis` moves them back once, in
  `update_nbk` / `update_ardfm`, before normalisation. Proof: the four quarters of each year
  2020-2024 now add up to the IMF annual current account to 1 mln USD. Enterprise surveys, stocks
  «as at the 1st» and DEPOSIT_RATE (evidence inconclusive) are unchanged.
- *Point-in-time stocks restated to the period start.* `processed_store.write_processed` now passes
  `observation_type` to `periods.normalise`; the five National Fund portfolio series return to their
  quarter-end dates (2026-06-30, not 2026-04-01).
- *2015 lost from six regional labour tables and EMPLOYED_TOTAL.* The year pattern rejected the
  footnoted header «20152)»; `year_regex` now allows a footnote digit (16 datasets; re-parsed from the
  archived workbooks: only the 2015 column is added, nothing else changes).
- *Minfin.* Month names matched by stem («январь-феврал отчет» had dropped Jan-Feb 2026 from six
  STATE_*_YTD series); `update_minfin.keep_unlisted_history` carries over periods the gov.kz listing no
  longer serves; 49 lost points restored from the 33 archived bulletins (no conflict with any value
  already held), incl. Jan-Feb 2025 for 23 series, Jan-Feb 2026 for six, TAX_ARREARS_TOTAL on 1 January 2024 and
  2025, and the 2021-2022 annual columns of older editions for 18 annual series.
- *Expenditure GDP components 2010-2013.* `gaps_filled_from` fills the Taldau gap in GFCF,
  HOUSEHOLD_CONSUMPTION, NET_EXPORTS, GROSS_ACCUMULATION, TOTAL_CONSUMPTION_EXPENDITURE and the three
  volume indices from table 4439 — only while the two agree on every shared year (15 of 15, to 1e-16).
- *Labels.* IMF WEO years stamped at 31 December like BNS (a date join returned nothing before), and
  every year from the vintage's COUNTRY_UPDATE_DATE on is labelled «IMF WEO estimate/projection» in
  `transformation`; year-to-date series say so in `transformation` (34, was 1); unit strings of CPI,
  GDP_DEFLATOR and three volume indices now say «index, … = 100»; core CPI notes say monthly;
  youth unemployment is ages 15-34; stale `sources.yaml` entries carry `current_source`.

**Source errors are kept as published** and listed in `config/source_issues.yaml` (export tonnage
June 2026, NBK money 2021-12..2022, 2021 non-oil deficit, eurobonds 2022-Q4, …); DATA_CATALOG.md
shows each with a status that flips when a source corrects it. Tests 364 → 382.

## 2026-09-25 — model data, step 1 (what the archive allows): BOP from 2000, bilateral real exchange rates (user: «Сделай пункт 1»)

The network to the sources was closed in this session (stat.gov.kz, nationalbank.kz, kase.kz, gov.kz
answer 403 through the environment's proxy), so only what the archived downloads already hold was added.

- **Balance of payments from 2000-Q1 (was 2020-Q1).** CURRENT_ACCOUNT_BALANCE and the four BOP_* lines
  now read formId=481 for the 80 quarters before formId=324's first (`nbk._bop_history`). 481 was
  rejected earlier because it serves two amounts for some quarters -- but only from report_date
  2023-04-01, inside 324's range. Each download is checked: one amount per early quarter, the
  identity goods + services + primary + secondary = current account in every one of them, and 481
  equal to 324 on every quarter both carry unambiguously; any failure leaves the history out and says
  so in the manifest. The four quarters of every year 2000-2024 add up to the IMF WEO annual current
  account within 0.8 mln USD (test: tests/test_date_basis.py).
- **Six new NBK series from formId=299** (436 indicators): RER_USD, RER_RUB, RER_EUR, RER_CNY --
  bilateral real exchange rates of the tenge -- and REER_EX_OIL, NEER_EX_OIL. Monthly from 1995-01,
  December 2016 = 100, a rise is a real appreciation. Built from the form archived 2026-09-03 (to
  2026-06); the next CI run refreshes them.

**Still needed for QPM / BVAR, blocked on network access:** CPI by group (food / non-food / services /
regulated, Taldau terms not yet identified), monthly PPI, the base rate before 2024-10, the official
exchange rate before 2021-05, M0-M3 and bank rates before 2021-12 (most NBK forms serve a window from
2023-01 by default -- the date parameter still has to be found live), TONIA before 2026-02, the
government yield curve, rates and volumes of new loans, quarterly unemployment before 2023, a monthly
industrial production index.

## 2026-09-25 — model data, step 1 continued (network opened): BNS prices, production, labour

Queries found through Taldau's own endpoints (getSearchPageGridData, GetPeriodList, GetSegmentList)
and checked against BNS's releases before wiring in. 451 indicators.
- **CPI by group**, monthly from 2011-01, month-on-month and year-on-year: CPI_FOOD, CPI_NONFOOD,
  CPI_SERVICES, CPI_UTILITIES, CPI_REGULATED_UTILITIES (+ _YOY). December y/y 2011-2025 equal BNS
  element 1548 in every year (Dec 2022: food 125.3, non-food 119.4, services 114.1).
- **PPI_MONTHLY / PPI_YOY_MONTHLY** from 2011-01 (Dec/Dec 2011-2025 equal element 1626).
- **IND_PROD_MONTHLY_YOY / _MOM** from 2014-01 (October 2025: 107.1 / 99.4 as released).
- **UNEMPLOYMENT** from 2001Q1 (was 2023Q1-2025Q2, stale): element 5830 «Основные индикаторы рынка
  труда»; identical to the old cube on all 10 shared quarters. Its 2014 column is headed «20142)» —
  the same footnote trap as the 2015 labour tables; the validator's duplicate-date check caught it.
- **AVG_WAGE_1T_QUARTERLY** from 2015Q1 (element 5674, form 1-Т) — a different coverage from
  AVG_WAGE_QUARTERLY (2026Q1: 461 486 against 445 068 KZT), so a separate series.

## 2026-09-25 — model data, step 1 continued: KASE as the eighth agency, long NBK histories

Sources found live and checked before wiring in (research notes in the PR); 462 indicators.
- **KASE (new agency, `scripts/fetchers/kase.py`, `update_kase.py`).** kase.kz now has JSON/xls
  surfaces. **TONIA** moved here from the NBK widget: daily by TRADE date from 2001-09-02 (was
  2026-02-24 onward, publication-dated, weekends filled). **GS_YIELD_3M/6M/1Y/2Y/5Y/10Y**: monthly
  averages of KASE's daily Nelson-Siegel zero-coupon curves from 2019-11; the tenors computed from
  the file's parameters equal the curve KASE plots within 0.001 pp.
- **BASE_RATE**: all 91 decisions from 2015-09-02 — the endpoint needs both `from` and `to`; with
  one or none it serves the last 15.
- **EXCHANGE_RATE** from 1999-11 (was 2021-05) and new **EXCHANGE_RATE_EUR / _CNY / _RUB**: the NBK
  archive report (one request, all currencies). The 1 386 accumulated USD points are unchanged; the
  archive also carries 07.05.2021 correctly. Each run now reads the last 45 days and accumulates. The
  report's first rows (1999-10-19..21) are malformed and dropped. The isolated-spike guard now looks
  only at the dollar's last 60 days: over the history it fired on 2015-08-25, which is real.
- **M0-M3, MONETARY_BASE, DEPOSITS_TOTAL** from 1994 (was 2021-12): NBK page records. This also
  **fixes the 2021-12..2022-12 values** that open-data form 51 got wrong (M3 4.5 trn → 28.7 trn); the
  entry is gone from `config/source_issues.yaml`. From 2023 the two sources agree on every month.
- **DEPOSIT_RATE** from 1996-12 (page records) — and one month earlier than before: form 268 stamps
  month m at m+1 like the other flows (42 of 44 months equal after the shift), which the audit had
  flagged as unproven.
- **LOAN_RATE_ISSUED_LEGAL_KZT / _INDIVIDUAL_KZT** from 1997-01 (form 486, `date_basis`); the API
  lacks a few months in 2007-09 and 2014.

## 2026-09-25 — model data, step 2 (external block), part 1: Russia, the United States, world prices

New agencies `cbr`, `eec`, `fred` (one updater, `update_foreign.py`, `scripts/fetchers/foreign.py`);
472 indicators. Every source checked live against known values before wiring in.
- **Russia:** RU_KEY_RATE (Bank of Russia SOAP KeyRateXML, 66 changes from 2013-09-17, dated by
  effective date); RUB_USD (official, daily from 1998); RU_CPI_MOM / RU_CPI_YOY (EEC, monthly from
  2005 — Rosstat is unreachable from the runner; EEC y/y equals the Bank of Russia's table within
  0.05 in 156 of 156 months); RU_GDP_REAL (IMF QNEA, 2021 prices, NSA, from 2014-Q1 — 2011-13 are on
  another base). FRED's Russia series ended in 2021-22 and are not used.
- **United States (FRED, no key):** US_FED_FUNDS, US_TREASURY_2Y, US_TREASURY_10Y (monthly averages),
  US_CPI (SA), US_GDP_REAL (chained 2017 USD, SAAR).
- **World prices:** item-level WB_COMMODITY_PRICES_MONTHLY (71 series) and
  WB_COMMODITY_INDICES_MONTHLY (16) from 1960-01, from the monthly Pink Sheet.

## 2026-09-25 — model data, step 2 (external block), part 2: China, euro area, EAEU, foreign demand

New agencies `nbs`, `ecb`, `derived`; 480 indicators. Checked live against known values.
- **China:** CN_CPI_YOY (IMF CPI, % y/y, from 1994 — FRED's China series stopped in 2023-25);
  CN_GDP_REAL_YOY (NBS, single-quarter y/y, from 1993 — via the new data.stats.gov.cn JSON endpoint,
  the old easyquery API is behind a WAF; the IMF's QNEA volume for China breaks its base in 2026).
- **Euro area (ECB Data Portal):** EA_HICP_YOY (dataflow HICP — ICP ended at 2025-12), EA_GDP_REAL
  (chain-linked 2015, SCA, EA20), EA_DEPOSIT_RATE (69 changes from 1999).
- **EAEU:** BY_CPI_YOY, KG_CPI_YOY from the same EEC file as Russia.
- **FOREIGN_DEMAND_YOY:** real GDP growth of the euro area, China and Russia weighted by Kazakhstan's
  2023-2025 export shares (43.2 / 18.6 / 11.7 %, rescaled; BNS indicator 312101, recomputed from the
  2024-2025 table), quarterly from 2015-Q1. Weights and caveats in `config/foreign_demand.yaml`.

## 2026-09-25 — model data, step 5: the gravity model

New module `scripts/fetchers/gravity.py` (item-level, `config/dims.yaml`; items are ISO3 partner
codes), new agency `wits`, static CEPII tables in `data/reference/`. All checked live.
- **KZ_EXPORTS_BY_PARTNER / KZ_IMPORTS_BY_PARTNER** (BNS 312101, thousand USD, 2020–2025, 233
  partners): each year from its final July edition (the 2021 edition's second sheet gives 2020);
  country rows sum exactly to «Всего» (2025 exports 79.23 bn: China 15.20, Italy 15.64, Russia
  8.25). A partner with a blank cell is a zero flow, stored as 0 (PPML needs the zeros). Russian
  names → ISO3 through the new `dictionaries/partner_countries.csv` (235 names; an unknown name
  stops the dataset).
- **WITS_KZ_EXPORTS/IMPORTS_BY_PARTNER** (UN Comtrade via WITS, 1995–2023): the long history. Equal
  to BNS for EAEU partners but well below it for non-EAEU flows in 2020–2022 (world exports 2021:
  53.1 vs 60.3 bn) — splice to BNS from 2020.
- **KZ_TARIFF_AVERAGES** (MFN and applied, simple and weighted, 1996–2023; applied simple 4.26 %
  in 2023) and **KZ_TARIFF_APPLIED_BY_PARTNER** (2004–2023).
- **WDI_GDP_USD, WDI_GDP_CONST_USD, WDI_POPULATION** (World Bank API, 2000–2025, 213–217
  economies, aggregates dropped).
- **data/reference/cepii_geodist_kaz.csv** (GeoDist: distances, contiguity, language, colonial
  ties) and **cepii_gravity_kaz.csv** (Gravity V202211, 1992–2021: harmonic weighted distance,
  RTA/FTA, WTO/GATT, EU, sibling/dependency links). Static research releases, not refreshed.

## 2026-09-25 — model data, step 3: potential output and the output gap

Production-function inputs; 490 indicators. All checked live against BNS publications.
- **Capital (BNS form 11, Taldau, 2000–2025, billion KZT):** FIXED_ASSETS_GROSS (216 944 in 2025),
  _GROSS_START, _NET (114 878), _COMMISSIONED, _DEPRECIATION, FIXED_ASSETS_WEAR (47.0 %),
  FIXED_ASSETS_RENEWAL. Tangible assets only (term 455728 — the Taldau default adds intangibles:
  222 829). 2025 equals the publication «Основные фонды РК (2025)» to the tenge. **Book values at
  historical cost incl. revaluations (2024: +22.5 %)** — not a volume measure of K; deflate or build
  a perpetual-inventory stock from GFCF before using it in a production function.
- **Item-level (new fetcher `taldau`, `scripts/fetchers/taldau_dims.py`):** FIXED_ASSETS_GROSS/NET/
  WEAR_BY_SECTION (ОКЭД A–T, 2000–2025; mining 2025: 67.7 trn, wear 59.9 %), FIXED_ASSETS_GROSS_BY_ASSET
  (buildings, structures, machinery 98.2 trn, other, biological), EMPLOYED_BY_SECTION_LONG (2001–2019:
  adds 2001–2009 to EMPLOYED_BY_SECTION; equal on 2010–2019 once T and U — folded into S by element
  5831 — are added back). Children are checked to sum to the total. Dictionary okved_sections gains U.
- **Hours:** HOURS_WORKED (million man-hours, 2000–2012 and 2017–2025), HOURS_WORKED_QUARTERLY (from
  2016-Q1), HOURS_PER_EMPLOYEE (1 835 h in 2025). The annual 2013–2016 values exist only on a Taldau
  segment with ~8 % lower coverage (2017: 6 353 summed over quarters vs 6 848) and are NOT spliced in —
  a splice would show +9 % "growth" in 2017.
- **CAPACITY_UTILIZATION_BY_SECTOR** (NBK form 369, 13 sectors + total, 2016-Q2 onward; new fetcher
  `nbk_survey`); TOTAL equals the scalar CAPACITY_UTILIZATION in every quarter.
- **Not added:** a Eurobond country-risk spread. The one free daily price source found (the Deutsche
  Börse web API) authenticates requests with a key scraped from the site's JavaScript — the pipeline
  does not reproduce another site's client authentication.

## 2026-09-25 — model data, steps 4, 6, 7: nowcasting, МОБ/CGE, sovereign rating

497 indicators. Checked live.
- **Nowcasting — monthly state-budget taxes, 2018-01 to 2026-07** (Minfin Statistical Bulletin,
  'табл 3', million KZT, year-to-date): STATE_TAX_REVENUE_YTD, STATE_CIT_YTD, STATE_PIT_YTD,
  STATE_SOCIAL_TAX_YTD, STATE_VAT_YTD, STATE_EXCISE_YTD (+ December 2016-17). The bulletin series
  so far read only the listing's first page (to 2025) and missed the older «Statistical Bulletin»
  titles; now all pages are read (91 editions) and the period of every column is read from its
  header across three layouts (discrete quarters 2020-21 are cumulated). Only 2026-04 is missing
  (no edition). Tax 2024 = 19 700 517 mln KZT, equal to KGD's figure to the thousand. The archive
  keeps each edition's 'табл 3' as JSON rather than the ~70 MB of workbooks.
- **Ratings:** WGI_GE/RQ/RL/CC/VA/PV (Worldwide Governance Indicators, estimate, all economies,
  1996-2024; the codes changed to GOV_WGI_*.EST in the 2025 revision; KAZ 2024: GE 0.15, RL −0.38,
  VA −0.82); EXTERNAL_DEBT_SERVICE_SCHEDULE (NBK form 346: principal and interest due by sector and
  horizon; principal sums to EXTERNAL_DEBT — 182 778 mln USD at 2026-04-01 — enforced; 43.0 bn due
  within 12 months incl. on demand; the API keeps two vintages, older ones are carried forward);
  GG_INTEREST (general government interest, GFS row 24, quarterly). No machine-readable source of
  the rating history itself was found.
- **МОБ / CGE (CAEM):** `scripts/build_io_tables.py` → `data/reference/io/`: symmetric input-output
  tables (68 products, 10 tables incl. A and the Leontief inverse) and supply-use tables (125 × 72)
  for 2021-2024, long gzip CSV. L = (I − A)⁻¹ checked on every build (≤ 4e-15). BNS's A divides by
  output + imports. Run after each December release; not part of the daily run.
- **Not done yet:** household income/expenditure by decile (BNS 18651 gives decile income shares;
  Taldau expenditure by decile has only D1/D10 before 2024).

## 2026-09-25 — income by decile (CGE/CAEM calibration, distribution)

New fetcher `scripts/fetchers/bns_living.py` (every edition of BNS «Основные показатели
дифференциации доходов населения», listing 18651, plus Taldau history); 499 indicators.
- **Item-level, D01–D10:** INCOME_SHARE_BY_DECILE (annual 2011–2025) and _QUARTERLY (2011-Q1 to
  2026-Q1; Taldau lacks 2017-Q1..Q3 and 2021-Q2); INCOME_MEAN_BY_DECILE (mean monthly money income per
  capita, annual 2022–2025; 2025: 44 360 to 265 626 KZT) and _QUARTERLY (2022-Q3 on);
  INCOME_UPPER_BOUND_BY_DECILE (the decile cut-offs) annual and quarterly; HH_EXPENDITURE_BOTTOM_TOP_DECILE
  (money expenditure of D01 and D10 by item, 2001–2024, Taldau 704518 — equal to the 2024 edition's
  table 10 to the tenge).
- Shares add to 100 in every period (enforced). Taldau's annual shares equal the editions on all 30
  common points; its quarterly shares differ in the second decimal on 16 of 122 and miss quarters, so
  they are used only before the first quarterly edition (2022-Q3).
- **Fixed: GINI_COEFFICIENT, DECILE_INCOME_RATIO, POVERTY_DEPTH, POVERTY_SEVERITY held ONE quarter
  each** (the fetcher saw only the edition linked from the section page). Now 15 quarters from the
  editions, and the Gini 57 quarters with Taldau's history from 2011 (equal to the editions on every
  common quarter). New: GINI_COEFFICIENT_ANNUAL (2001–2025; 0.339 in 2001, 0.291 in 2025) and
  DECILE_INCOME_RATIO_ANNUAL (2011–2025).
- Quintiles are not stored separately: each quintile is two adjacent deciles (shares add, bounds are
  the even decile cut-offs).

## 2026-09-26 — sovereign Eurobond spread (country risk premium)

New fetcher `scripts/fetchers/kase_eurobonds.py`; 501 indicators.
- **Source:** KASE's daily settlement-price valuations of every Ministry of Finance Eurobond (free
  files, plain GET): the daily xls from 2024-08, the CMS archive of zips before (2014-2024, three
  layouts, columns found by header). Last valuation of each month. Other free sources were checked
  and rejected (AIX: no trades; LSE: history behind a signed widget; Deutsche Börse: requests need
  headers computed from a key in the site's JavaScript — not reproduced; NBK/IMF/FRED/WB: no series).
- **Item-level:** EUROBOND_PRICE_BY_ISSUE, EUROBOND_YTM_BY_ISSUE (all MinFin Eurobonds, USD and EUR,
  2014-11 on) and EUROBOND_SPREAD_BY_ISSUE (USD bonds over the FRED constant-maturity Treasury curve
  DGS5/7/10/20/30, interpolated at the remaining maturity on the valuation date).
- **Headline:** KZ_EUROBOND_SPREAD (bp) and KZ_EUROBOND_YIELD — the 2044 bond to 2020-10, the 2045 bond
  from 2022-08, **2020-11 to 2022-07 left missing** (only stale/indicative 2044 quotes; listed in
  `config/source_issues.yaml`). 2015-08 377 bp, 2016-01 348, 2020-03 276, 2022-10 312, 2026-09 65.
- **Checks:** YTM reproduces KASE's to 0.01 pp (a mismatch above 0.1 pp stops the run — it would mean a
  wrong coupon/maturity or column); an independent re-computation agrees on all 121 benchmark months
  within 0.9 bp; LSE's last trade in the 2045 bond (27.07.2026) is within 0.3 points of KASE's value.
- Not EMBI: one bond, valued by KASE. Accumulates: the first run back-filled 2014-11..2026-09; daily
  runs fetch only missing months and the last two.

## 2026-09-26 — country risk: short Treasury tenors, and the tenge's side of UIP

507 indicators.
- **Eurobond spreads:** the Treasury curve now has 1/2/3-year points (FRED DGS1/2/3), and a bond in its last
  year gets no spread (EMBI's 12-month rule). The 2020-11..2022-07 gap of KZ_EUROBOND_SPREAD stays: the short
  2024/2025 bonds are quoted in that window but are no better — 12-18 bp in April-June 2022, ninefold
  disagreement in 2022-09 and NEGATIVE spreads (to -112 bp) every month 2023-04..2024-04 while the 2045 bond
  stood at 120-170 bp (`config/source_issues.yaml`).
- **SWAP_1D** (KASE «SWAP-1D (USD)», daily from 2014-06): one-day USD/KZT FX swap rate. No KASE methodology is
  published; in 2024-2026 it tracks TONIA - fed funds, in 2022-12..2023-06 it sat at TONIA + 1 (15-17 %) while
  the differential was 11-12 %.
- **Derived (monthly):** KZT_USD_RATE_DIFF_ON (TONIA - fed funds, from 2001), KZT_USD_RATE_DIFF_1Y and _10Y
  (KASE zero-coupon curve - Treasury constant maturity, from 2019-11), and KZT_CARRY_EXCESS_RETURN — the
  ex-post excess return of tenge over dollars, (TONIA - FF) - 1200 ln(S_m/S_m-1): its mean is the average UIP
  premium (2016-2026: 7.1 % p.a., s.e. 3.1; 2023-2026: 10.9, s.e. 4.6); devaluation months -199 (2014-02) and
  -276 (2015-08). New US_TREASURY_1Y (FRED GS1).
- **Not available openly:** expected depreciation (NBK open data has inflation expectations only), so the
  ex-ante currency premium is not published as a series — it is the differential minus expected depreciation,
  to be estimated in the model.

## 2026-09-26 — first full run of the extended pipeline; BNS energy format change

- `update_all.py` end to end with every change of 2026-09-25/26: 56 min, 663 of 664 updates ok.
- The failure was the source: BNS replaced element 8582 (FINAL_ENERGY_CONSUMPTION) — a json_cube list — with a
  dump of the xlsx ({sheet: rows}). `fetch_final_energy_consumption` now reads both; the new file carries the
  series from 1991 (was 2015), 2015-2025 unchanged (2022 rounded to 41 156.45 from 41 156.454). An unknown shape
  is a StructuralChangeError, not an AttributeError.

## 2026-09-26 — model_data/: model-ready panels (derived)

New top-level `model_data/` (derived by this repository, like `analysis/`): `scripts/build_model_data.py`
reads `data/unified/` and `model_data/spec.yaml` and writes `monthly.csv` (1994-01 on, 40 variables),
`quarterly.csv` (35 variables + production function), `annual.csv` and `VARIABLES.md` (a card per variable).
Chained price and production indices, YTD flows decumulated, stocks moved from "as at the 1st" to end of
month, policy rates as monthly means of the step function, STL (robust) seasonal adjustment where the source
publishes none (BNS quarterly accounts and FRED are used as published), `_yoy`/`_saar` columns.
- **Capital stock:** perpetual inventory at 2010 prices from 2000 (annual GFCF chained with its volume index;
  δ = 8.3 %, the median BNS book depreciation rate outside the 2019-21 revaluations; Harberger start), quarterly
  from 2010 with BNS SA GFCF benchmarked to the annual figures (the 2010-22 quarterly accounts are an older,
  higher vintage). K/Y 1.3 (2010) -> 2.1 (2026).
- **TFP** (Solow residual, α = 0.665 from the QNA labour share): −17 log points 2010-Q1..2026-Q1; −12 to −22 for
  δ between 12 % and 5 % — heavy investment (Tengiz, infrastructure) with little output yet.
- Checks: chained CPI y/y vs BNS CPI_YOY 0.07 pp mean gap (0.35 max, m/m rounding); our STL on real GDP vs
  BNS's own SA: q/q correlation 0.91.
- Found on the way: the scalar EMPLOYED_QUARTERLY holds only 2 quarters (the item-level
  EMPLOYED_BY_SECTION_QUARTERLY has 2010 on and is used here).

## 2026-09-26 — models/: gravity, BVAR, r* (derived)

New top-level `models/` with `scripts/models/{common,gravity,bvar,rstar}.py`; each writes a Russian report,
charts and CSVs. Not part of `update_all.py`.
- **Gravity (PPML), 2000–2025:** WITS flows to 2019, BNS from 2020 — WITS 2020–22 imports are incomplete (2020:
  22 bn USD vs BNS 39 bn); Russia/Belarus 2010 dropped (customs-union gap in WITS: imports 24.0 vs official 31.1
  bn). Partner FE: the EAEU adds nothing over the CIS free-trade area (imports −3 %, 95 % CI −18…+15 %; exports
  −7 %). Year-FE elasticities: GDP 0.78 / 0.96, distance −1.13 / −0.65 (exports / imports). The trade-weighted
  applied tariff does not identify σ (β = +3.3, s.e. 2.3).
- **BVAR, 2011Q2–2026Q1:** 7 variables, external block exogenous, λ = 0.75, μ = 5, crisis-quarter scale s = 5
  (log ML +91 over s = 1). Pass-through 0.11 at 4 quarters, 0.19 at 8 (0.24 / 0.29 without the crisis
  scaling); +1 pp TONIA: prices −0.18 % at 8 quarters, GDP −0.12 % at 4; +10 % Brent: prices +0.7 % at 8.
- **r\* and output gap, 2012Q1–2026Q1:** r* 1.4 % in 2026Q1 (±6 pp state s.d.), real rate 6.3 %, P(r > r*) 80 %;
  trend growth 4.2 %; gap −0.5 % (production function −0.1 %, HP +0.5 %; the three gaps correlate at 0.93+).
  Maximum likelihood without priors: gap persistence 0.14, a_r −0.04, z flat at its initial value.
- Corrected `data/reference/README.md`: CEPII `col_dep_ever` is 0 for every KAZ pair (it said KAZ–RUS = 1).

## 2026-09-26 — project_knowledge/ cut from 6.6 MB to 0.29 MB to fit the Claude Project's context

Nothing removed from the data: full histories stay in `data/unified/`, full metadata in `metadata/`.
- `latest/macro_latest.csv`: was a copy of `macro_wide.csv` (5.5 MB, every series since 1947); now one row
  per series — name, agency, frequency, unit, first date, n, latest value, previous value, year-ago value
  (102 KB).
- `latest/macro_metadata.json` (535 KB) removed; `DATA_DICTIONARY.md` is a table per agency with the first
  sentence of the methodology (359 → 73 KB); `DATA_CATALOG.md` is a summary plus the known source problems
  (86 → 3.5 KB), the per-series list being `macro_latest.csv`.
- `UPDATE_LOG.md`: entries 2026-08-30 .. 09-15 moved to `docs/UPDATE_LOG_ARCHIVE.md` (357 → 48 KB here).
- New `models/{gravity,bvar,rstar}.md`: the model reports, text only.
- `tests/test_project_knowledge.py` fails if the folder passes 600 KB.
