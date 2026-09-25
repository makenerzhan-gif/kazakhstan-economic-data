# Kazakhstan Economic Data Pipeline

Automated collection, validation, processing, and versioning of official
Kazakhstan macroeconomic data from eight sources — Bureau of National
Statistics (БНС), National Bank of Kazakhstan (НБ РК), Ministry of Finance
(Минфин), the Agency for Regulation and Development of the Financial Market
(АРРФР), the Kazakhstan Stock Exchange (KASE: TONIA, the government securities
yield curve), the IMF, and, for world commodity prices, the World Bank (Pink Sheet,
Commodity Markets Outlook) and the U.S. EIA (Short-Term Energy Outlook) — into a
unified dataset, with a manual bridge into a Claude Project for analysis.

```
БНС + НБ РК + Минфин + АРРФР + KASE + IMF + World Bank + EIA → RAW → VALIDATION → PROCESSED →
METADATA → UNIFIED DATASET → GitHub → (manual "Sync now") → Claude Project "Экономика Казахстана"
```

## Scope

499 indicators (see `config/indicators.yaml`), all connected end-to-end
against live official sources — past the original 18-indicator pilot and its
100-150 indicator target (MASTER TASK section 17). No econometric modeling
yet; see `project_knowledge/UPDATE_LOG.md` for the dated history of how the
dataset grew and what was verified at each step.

For the gravity model of Kazakhstan's trade, item-level datasets keyed by ISO3
partner code (`config/dims.yaml`): trade by partner (BNS from 2020, WITS/UN Comtrade
1995–2023), partner GDP and population (World Bank WDI), tariffs (WITS); distances and
bilateral dummies (CEPII) are static tables in `data/reference/`. Input-output and
supply-use tables (BNS, 2021–2024) are built into `data/reference/io/` by
`scripts/build_io_tables.py`.

## Repository layout

```
data/raw/{bns,nbk,minfin,ardfm,imf}/       append-only, date-stamped downloads, never edited/deleted
data/processed/{bns,nbk,minfin,ardfm,imf}/ cleaned + transformed series
data/unified/                              macro_long.csv (long format) + macro_wide.csv (wide format)
metadata/{bns,nbk,minfin,ardfm,imf}/       one JSON per indicator (source, methodology, dates, ...)
metadata/revisions/                        logged old->new value changes, never overwritten
dictionaries/                              data dictionary source files
project_knowledge/                         the ONLY folder meant to be synced into the Claude Project
scripts/                                   update_<agency>.py, update_all.py, scripts/lib/*
tests/                                     pytest suite
reports/                                   update_report_YYYY-MM-DD.md per run
config/                                    indicators.yaml, sources.yaml, frequency.yaml
.github/workflows/update.yml               scheduled automated run
```

## Running locally

Requires [Git LFS](https://git-lfs.com/) — `data/raw/bns/*.xlsx` and
`data/raw/minfin/*.xlsx` are LFS-tracked (BNS trade data alone is 50-90MB per
file and republishes full history monthly; see `project_knowledge/UPDATE_LOG.md`
for why). Run `git lfs install` once, then clone/pull as normal.

```bash
pip install -r requirements.txt
python scripts/update_all.py       # full pipeline
python scripts/update_bns.py       # single agency
pytest tests/ -q
```

## Model sync (local, Windows only)

`config/model_map.yaml` is the contract between the Excel GDP model
(`1_Model_GDP_p_a_2025_…_rev_*.xlsx`, kept outside this repo) and the unified
dataset: one entry per pipeline variable, naming the workbook cells that should
hold its annual value and the rule that turns observations into one number per
year. `scripts/model_sync.py` reads the workbook and reports, per cell and year,
whether the model already holds the pipeline value. A cell holding a formula is
only ever compared (the model computes it); a cell holding a number is rewritten
by `--apply` when it differs, through a private Excel instance
(`scripts/lib/excel_apply.ps1`), with a cell comment and a row in the model's
own «Журнал_правок» sheet. The source workbook is never modified in place.

```bash
python scripts/model_sync.py                       # check against model.default_file
python scripts/model_sync.py --model path.xlsx --apply --out path_synced.xlsx
```

This step is deliberately not part of `update_all.py`: the model is a hand-run
file on the analyst's disk, not a pipeline artefact.

### Every number has a source

`config/manual_inputs.yaml` records the provenance, vintage, owner and refresh rule
of every block of numbers in the model that is not a pipeline series — the
history loaded by hand before 2025, the ministries' forecasts («Прогнозы ЦГО»),
the author's assumptions, the reference sheets — and flags the few literal numbers
that sit where a formula or a source would be expected (`kind: review`).
`scripts/model_coverage.py` walks every literal number in the workbook and reports
what neither `model_map.yaml` nor `manual_inputs.yaml` claims; `--strict` exits 1
when anything is unclaimed. `config/calendar.yaml` holds the release rhythms the
sources do not publish machine-readably (CMO, Pink Sheet, STEO, WEO, the PSER
document, the BNS express releases) and the refresh procedure;
`scripts/build_calendar.py` joins it with the «Дата следующей актуализации» the BNS
tables state in their own metadata sheet (kept in `metadata/bns/*.json`) into
`project_knowledge/CALENDAR.md` — the next date for every series the model reads,
overdue ones flagged. `update_all.py` rebuilds it daily.

Refresh procedure, in order (also in `config/calendar.yaml`):

```bash
python scripts/update_all.py
python scripts/model_sync.py
python scripts/model_sync.py --apply --out <copy>
python scripts/model_coverage.py --strict
python scripts/build_calendar.py
```

## Item-level series (breakdowns)

`macro_long.csv` promises one value per (date, variable). Breakdowns — GVA by
ОКЭД section and by industry division, GDP by expenditure component, income
components by section, the non-observed economy, GVA by form of ownership, and
the regional series (gross regional product and GVA by section and region,
volume indices, population by region and settlement type, the labour market,
fixed capital investment), physical output by product, production indices by
activity and grain by region — have one value per (date, region, variable,
item), so they live in a parallel layer with the same rules: `config/dims.yaml`
(115 datasets: 40 annual, 14 year-to-date, 19 discrete-quarter and 35 more from the rest of the
national-accounts page, all from 55 BNS dynamic tables read from their xlsx or legacy xls
export, two from the BNS export workbook by commodity group, four from the World
Bank's Pink Sheet and Commodity Markets Outlook, one from the U.S. EIA Short-Term
Energy Outlook), `scripts/update_dims.py` (fetcher chosen by each dataset's
`fetcher` or agency; `--only wb eia` or dataset ids to run a subset),
`scripts/fetchers/bns_dims.py` (five sheet layouts), `scripts/fetchers/bns_trade.py`
(HS-prefix groups summed over the regional blocks, national total re-checked every
month), `scripts/fetchers/wb.py`,
`scripts/fetchers/eia.py`, `scripts/lib/dims.py`, `data/processed/dims/<id>.csv`,
and `data/unified/macro_dims_long.csv.gz` (gzip-compressed — 217 597 rows are 61 MB plain;
`macro_long`'s columns plus `item_code`,
`item_name`; `region` is `national` for the country row, a code from
`dictionaries/regions.csv` for a region, and `world` — with `country` WLD — for
the world benchmark prices). Item codes come from the dictionaries
(`okved_sections`, `expenditure_items`, `industry_divisions`, `products`,
`hs_export_groups`, `wb_commodities`, `wb_commodity_indices`; see
`dictionaries/README.md`); a data
row whose label matches no dictionary entry stops that dataset loudly (sheets
that also list districts or products outside the dictionary say `strict: false`
and skip them). Forecast observations (the CMO's `2026f`/`2027f` columns, STEO
months after the release's last historical month) carry `transformation`
`forecast` so they are never mistaken for history.

Fourteen of the BNS datasets are quarterly siblings of annual ones (id suffix
`_QUARTERLY`; `periods: quarterly_ytd` or `quarterly_subcolumns` in
`config/dims.yaml`): the year-to-date columns and rows the same tables carry
beside the annual ones («1 квартал», «1 полугодие», «9 месяцев», «год») — GDP
by production (nominal, volume index, deflator; by section and by industry
division), GDP by expenditure (nominal, volume index, deflator), the income
account by section (compensation, other taxes, consumption of fixed capital,
operating surplus), the gross regional product by section and region and its
volume index by region — and the discrete «I–IV квартал» sub-columns of
employment by section. A quarterly observation is dated the first day of the
last quarter it covers (2024-07-01 for January–September 2024), as every
quarterly series in `macro_long.csv` is; Q4 is the year and equals the annual
sibling's value. The flow tables say `cumulation: year_to_date` and carry the
same `transformation` text as `GDP_NOMINAL`; the indices say in their unit
that they are year-to-date periods in % of the same period of the previous
year. Nothing is decumulated to discrete quarters.

Discrete quarters come from the only place BNS publishes them: the four tables
under the heading «Экспериментальная оценка Валового внутреннего продукта» on
the national-accounts dynamic-tables page — quarterly national accounts built
with IMF technical assistance (elements 283162 production, 283161 expenditure,
283160 income, 471384 regions; layout `year_quarters`, ids `QNA_*`, 19
datasets): GVA by section and GDP by expenditure component in current prices, in
average 2010 prices, as volume indices (quarter on the same quarter of the
previous year, plus the cumulative index and deflator sheets), seasonally
adjusted in current and 2010 prices; GDP by income and the income account by
activity (compensation, other net taxes, gross operating surplus); GVA by region
and section from 2019. Their cumulative twin sheets are not stored — they are the
running sums of the discrete quarters — but are re-read on every run and any
point where they disagree is reported (`cumulative_check`). **These tables carry
a different vintage of the 2010–2022 history**: the SNA-2008 recalculation their
annotation describes, which the dynamic annual tables (4439, 4435, 5927) and
Taldau do not carry — GDP 2010 is 9.4 % higher, 2017–2022 1.5–2.9 % lower;
2023–2025 are identical. Every `QNA_*` dataset says so in its `vintage` and
metadata, and nothing in the annual datasets changes because of it. The rest of the
national-accounts page is read too (35 datasets from 15 tables: gross output and the
production account by region, the annual SNA aggregates, labour productivity by section
and region, the oil-and-gas and commodity sector tables, the monthly short-term economic
indicator, GRP by region from 1993 and year-to-date, the non-observed economy and the
quasi-public sector by region, GDP components by institutional sector), so that every
table on that page is either in the pipeline, derivable from it, or a one-off publication
listed as such in `config/sources.yaml`. The model
carries the second vintage on a sheet of its own, «Факт_КНС» (annual values of
five QNA_* datasets, `fact_qna_*` mappings), which no model formula reads.
`update_all.py` runs it after the agency updaters. The World Bank also feeds one
scalar series, `OIL_PRICE_BRENT` (monthly Brent from the Pink Sheet, `scripts/update_wb.py`),
beside the IMF's `OIL_PRICE` (APSP average).

### Derived scalar indicators

Twelve scalar series are national totals that the item-level layer already
carries, so they are written from it rather than fetched a second time
(`derived_from` in `config/indicators.yaml`, `scripts/update_derived.py`, run
after `update_dims.py`): `EXPORTS`, `OIL_EXPORTS_VALUE`, `OIL_EXPORTS_VOLUME`
(the export workbook, read once), `IND_PROD` and its three sections (table
5792 instead of the cube that stopped at 2023), `INVESTMENT`, `POPULATION_BNS`,
`EMPLOYED_TOTAL`, `ELECTRICITY_PRODUCTION`, and `GDP_NOMINAL` (the «ВВП» row of
`GVA_NOMINAL_BY_SECTION_QUARTERLY` — the xlsx export of element 4439 instead
of its JSON cube). They keep their ids, units and
place in `macro_long.csv`/`macro_wide.csv`; `scale` only converts units, the
values are the published ones. Two more rules stop the same bytes being
fetched and stored again and again: every agency's `_download` is cached per
process, and `lib/raw_store.py` keeps one raw copy per distinct content — a
download that is byte-identical to a file already archived for that agency (any
indicator, any day) points at it in its dated manifest (`raw_file`) instead of
writing another copy; in a checkout without LFS content (the CI workflow) the
archived workbook is a Git LFS pointer, and the pointer's sha256 is what the
download is compared with. Revised content still lands as a new dated file, and
nothing archived is ever modified. The copies accumulated before this rule
(9.9 GB of 11.2 GB) were removed on 2026-09-15; `data/raw/dedup_2026-09-15.json`
maps every removed file to the file that holds its bytes; the 702 copies the CI
runs of 16–23 September archived again (LFS pointers compared by bytes, see
`lib/raw_store.holds_content`) were removed the same way on 2026-09-23
(`data/raw/dedup_2026-09-23.json`).

## Hard rules (see MASTER TASK for full detail)

- Never fabricate a data source, API endpoint, or dataset structure — every
  entry in `config/sources.yaml` must be backed by verified research.
- Never bypass CAPTCHA/login/anti-bot protection — mark the source as
  unavailable-automatic and note it for manual download instead.
- Raw data is never edited, and distinct content is never deleted — a new dated
  file for every revision; byte-identical downloads are stored once (see above).
- A structural change in a source stops that dataset's pipeline loudly
  (WHAT CHANGED / EXPECTED / ACTUAL / ACTION REQUIRED) rather than continuing silently.
- Production data is only updated if validation and tests pass.

## Manual step this pipeline cannot automate

GitHub Actions keeps `project_knowledge/` current automatically. Getting that
into the Claude Project "Экономика Казахстана" still requires a human to click
**Sync now** in the Project UI — there is no write API for Project Knowledge.
See `project_knowledge/README.md`.
