# Kazakhstan Economic Data Pipeline

Automated collection, validation, processing, and versioning of official
Kazakhstan macroeconomic data from seven sources — Bureau of National
Statistics (БНС), National Bank of Kazakhstan (НБ РК), Ministry of Finance
(Минфин), the Agency for Regulation and Development of the Financial Market
(АРРФР), the IMF, and, for world commodity prices, the World Bank (Pink Sheet,
Commodity Markets Outlook) and the U.S. EIA (Short-Term Energy Outlook) — into a
unified dataset, with a manual bridge into a Claude Project for analysis.

```
БНС + НБ РК + Минфин + АРРФР + IMF + World Bank + EIA → RAW → VALIDATION → PROCESSED →
METADATA → UNIFIED DATASET → GitHub → (manual "Sync now") → Claude Project "Экономика Казахстана"
```

## Scope

430 indicators (see `config/indicators.yaml`), all connected end-to-end
against live official sources — past the original 18-indicator pilot and its
100-150 indicator target (MASTER TASK section 17). No econometric modeling
yet; see `project_knowledge/UPDATE_LOG.md` for the dated history of how the
dataset grew and what was verified at each step.

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

## Item-level series (breakdowns)

`macro_long.csv` promises one value per (date, variable). Breakdowns — GVA by
ОКЭД section and by industry division, GDP by expenditure component, income
components by section, the non-observed economy, GVA by form of ownership, and
the regional series (gross regional product and GVA by section and region,
volume indices, population by region and settlement type, the labour market,
fixed capital investment), physical output by product, production indices by
activity and grain by region — have one value per (date, region, variable,
item), so they live in a parallel layer with the same rules: `config/dims.yaml`
(47 datasets: 40 from 36 BNS dynamic tables read from their xlsx or legacy xls
export, two from the BNS export workbook by commodity group, four from the World
Bank's Pink Sheet and Commodity Markets Outlook, one from the U.S. EIA Short-Term
Energy Outlook), `scripts/update_dims.py` (fetcher chosen by each dataset's
`fetcher` or agency; `--only wb eia` or dataset ids to run a subset),
`scripts/fetchers/bns_dims.py` (five sheet layouts), `scripts/fetchers/bns_trade.py`
(HS-prefix groups summed over the regional blocks, national total re-checked every
month), `scripts/fetchers/wb.py`,
`scripts/fetchers/eia.py`, `scripts/lib/dims.py`, `data/processed/dims/<id>.csv`,
and `data/unified/macro_dims_long.csv` (`macro_long`'s columns plus `item_code`,
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
`update_all.py` runs it after the agency updaters. The World Bank also feeds one
scalar series, `OIL_PRICE_BRENT` (monthly Brent from the Pink Sheet, `scripts/update_wb.py`),
beside the IMF's `OIL_PRICE` (APSP average).

## Hard rules (see MASTER TASK for full detail)

- Never fabricate a data source, API endpoint, or dataset structure — every
  entry in `config/sources.yaml` must be backed by verified research.
- Never bypass CAPTCHA/login/anti-bot protection — mark the source as
  unavailable-automatic and note it for manual download instead.
- Raw data is never edited or deleted, only appended to with a new dated file.
- A structural change in a source stops that dataset's pipeline loudly
  (WHAT CHANGED / EXPECTED / ACTUAL / ACTION REQUIRED) rather than continuing silently.
- Production data is only updated if validation and tests pass.

## Manual step this pipeline cannot automate

GitHub Actions keeps `project_knowledge/` current automatically. Getting that
into the Claude Project "Экономика Казахстана" still requires a human to click
**Sync now** in the Project UI — there is no write API for Project Knowledge.
See `project_knowledge/README.md`.
