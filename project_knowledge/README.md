# project_knowledge/ — what this folder is for

This folder is the **only** part of the repository meant to be synced into the
Claude Project "Экономика Казахстана" (Project Knowledge). It does not contain
raw data archives — those don't fit the context budget and aren't needed for
analysis, only the curated, current-state summaries below.

## Files in this folder

- `DATA_CATALOG.md` — what indicators exist, their status (connected / not yet), and where their processed data lives.
- `DATA_DICTIONARY.md` — one entry per variable: definition, unit, source, formula, last update.
- `SOURCES.md` — per-agency source status: API/CSV/XLSX, URL, access barriers.
- `UPDATE_LOG.md` — running changelog of what changed on each pipeline run.
- `latest/macro_latest.csv` — the most recent unified snapshot (wide format), small enough to read directly.
- `latest/macro_metadata.json` — metadata for every series in `macro_latest.csv`.

## IMPORTANT — syncing is manual

There is no API to write directly into Claude Project Knowledge. The bridge is
GitHub: this pipeline updates the files in this folder automatically (via
`.github/workflows/update.yml`), commits, and pushes — but **nothing after that
is automatic**. Project Knowledge only reflects what's in this folder once a
human clicks **Sync now** inside the Project "Экономика Казахстана" on claude.ai.

**Practical routine:** after any update you care about (or at least every few
days, and always before starting a new analysis session), open the Project →
Project knowledge → **Sync now**. If you skip this, the assistant in that
Project will be working from stale data even though GitHub is current.

## What NOT to expect here

- No raw archives (see `data/raw/` in the repo root — not synced).
- No econometric models yet — stage 1 of this pipeline stops at a clean,
  validated, documented unified dataset. Modeling is a deliberate later phase.
