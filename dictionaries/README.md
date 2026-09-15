# dictionaries/

Code lists for the item-level layer (`config/dims.yaml`, `scripts/lib/dims.py`).
Each file is a CSV with at least `code`, `name_ru` and `match`; `match` is a
case-insensitive regex applied to the *normalised* label of a data row or column
(`dims.normalise_label` for Russian sources — footnotes, Kazakh letters, Latin
look-alikes and wrapped hyphens folded away; `dims.normalise_label_en` for the
English-language World Bank and EIA files). Matching is strict: a label that
matches no entry, or more than one, is a structural change and stops the dataset.

| File | Codes | Used by |
|---|---|---|
| `okved_sections.csv` | ОКЭД sections A–T plus GOODS/SERVICES/IND aggregates, FISIM, GVA, taxes, GDP | national accounts by section, ownership, NOE, employment, investment |
| `industry_divisions.csv` | ОКЭД divisions 05–39 (+ IND) | GVA by industry division |
| `expenditure_items.csv` | GDP by expenditure components | expenditure tables 4435–4437 |
| `regions.csv` | 22 region codes (KZ → region `national`) | every regional dataset |
| `products.csv` | physical-output products (the GDP model's natural rows) | production in kind, 5814 |
| `wb_commodities.csv` | 69 World Bank Pink Sheet price series (`name_en`, `unit` too) | WB annual/monthly prices, CMO price forecasts, OIL_PRICE_BRENT |
| `wb_commodity_indices.csv` | 16 World Bank commodity price indices, 2010=100 | WB annual indices, CMO index forecasts |
| `hs_export_groups.csv` | 23 export commodity groups as HS prefixes (`hs` column, `\|`-separated) + TOTAL | exports by commodity group (value, tonnes) |

The World Bank files stopped carrying a mnemonic row, so the codes in the two
`wb_*` files are this repository's — modelled on the Pink Sheet mnemonics
(CRUDE_BRENT, COAL_AUS, NGAS_EUR …) — and each regex matches the label of both the
history file and the forecast table ("Logs, Cameroon" / "Logs, Africa"). The `unit`
column is checked against the units row of the price sheets: a series that changes
its unit stops the dataset rather than passing a number in a new scale.

`project_knowledge/DATA_DICTIONARY.md` is still generated from `metadata/**/*.json`
by `scripts/build_project_knowledge.py`; these files are inputs to the parsers, not
that rendered dictionary.
