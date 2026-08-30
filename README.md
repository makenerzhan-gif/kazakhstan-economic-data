# Kazakhstan Economic Data Pipeline

Automated collection, validation, processing, and versioning of official
Kazakhstan macroeconomic data from four sources — Bureau of National
Statistics (БНС), National Bank of Kazakhstan (НБ РК), Ministry of Finance
(Минфин), and the IMF — into a unified dataset, with a manual bridge into a
Claude Project for analysis.

```
БНС + НБ РК + Минфин + IMF → RAW → VALIDATION → PROCESSED → METADATA →
UNIFIED DATASET → GitHub → (manual "Sync now") → Claude Project "Экономика Казахстана"
```

## Stage 1 scope

18 pilot indicators (see `config/indicators.yaml`), all connected end-to-end
against live official sources, to prove the pipeline before scaling to the
full 100-150 indicator list. No econometric modeling in this stage — see
MASTER TASK section 17 for the stage-1 exit criteria.

## Repository layout

```
data/raw/{bns,nbk,minfin,imf}/       append-only, date-stamped downloads, never edited/deleted
data/processed/{bns,nbk,minfin,imf}/ cleaned + transformed series
data/unified/                        macro_long.csv (long format) + macro_wide.csv (wide format)
metadata/{bns,nbk,minfin,imf}/       one JSON per indicator (source, methodology, dates, ...)
metadata/revisions/                  logged old->new value changes, never overwritten
dictionaries/                        data dictionary source files
project_knowledge/                   the ONLY folder meant to be synced into the Claude Project
scripts/                             update_<agency>.py, update_all.py, scripts/lib/*
tests/                                pytest suite
reports/                             update_report_YYYY-MM-DD.md per run
config/                              indicators.yaml, sources.yaml, frequency.yaml
.github/workflows/update.yml         scheduled automated run
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
