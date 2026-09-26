# data/reference/

Static reference tables that no updater refreshes (their sources publish them as one-off
research releases). Written 2026-09-25 for the gravity model of Kazakhstan's trade; the
trade flows, partner GDP/population and tariffs they pair with are item-level datasets in
`config/dims.yaml` (KZ_EXPORTS_BY_PARTNER, WITS_KZ_*, WDI_*, KZ_TARIFF_*), keyed by the
same ISO3 codes.

| File | Rows | Source |
|---|---|---|
| `cepii_geodist_kaz.csv` | 224 partners of Kazakhstan | CEPII GeoDist (Mayer & Zignago 2011), `https://www.cepii.fr/distance/dist_cepii.zip`, rows with `iso_o = KAZ`: `dist` (km between the most populated cities), `distcap` (capitals), `distw`/`distwces` (population-weighted), `contig`, `comlang_off`, `comlang_ethno`, `colony`, `comcol`, `curcol`, `col45`, `smctry` |
| `cepii_gravity_kaz.csv` | 7 009 rows: partner × year, 1992–2021 | CEPII Gravity database V202211 (Conte, Cotterlaz & Mayer 2022), rows with `iso3_o = KAZ`: distances (`distw_harmonic` is the recommended one), contiguity, languages, religion, `col_dep_ever` (a former dependency relation; 0 for every KAZ pair in this release, so the gravity model codes the former USSR itself), `sibling_ever` (both ex-dependencies of the same hegemon, e.g. KAZ–KGZ), `fta_wto`/`rta_type` (trade agreements notified to the WTO), `gatt_d`/`wto_o`/`wto_d` (membership; Kazakhstan joined the WTO on 2015-11-30), `eu_d`, `diplo_disagreement`, `scaled_sci_2021` (Facebook social connectedness). Only years in which the partner existed (`country_exists_d = 1`) are kept; CEPII carries a second, non-existent row for a few split or merged states (DEU, ETH, IDN, MYS, PAK, SDN, VNM, YEM, ANT) |

Kazakhstan's EAEU membership (from 2015; customs union with Russia and Belarus from
2010) shows up in `fta_wto`/`rta_type`. Note that CEPII codes `sibling_ever = 0` for
KAZ–RUS because Russia was the hegemon itself; use `col_dep_ever` for that pair.

## io/

BNS symmetric input-output tables («Затраты - Выпуск», 68 products, sheets 1–10 incl. the
direct-requirements matrix A and the Leontief inverse) and supply-use tables («Ресурсы -
Использование», 125 products × 72 industries, sheets 1–8), 2021–2024, one long gzip CSV per
kind and year (`table, row_no, row_code, row_name, col_no, col_code, col_name, value`;
thousand KZT, coefficients in tables 9–10). Built by `scripts/build_io_tables.py`, which
also writes `editions.csv` (element id, publication date, the L = (I − A)⁻¹ check). BNS's A is
flows divided by total resources at basic prices (output + imports), not by output.

## nf_receipts_kgd_history.csv

National Fund receipts by tax, thousand KZT, year to date (`indicator_id, date, value_thousand_kzt,
source_url`; 1 433 rows, 2002–2025 without 2005–2006): KGD «Динамика поступлений налогов и платежей
в Национальный фонд» (https://kgd.gov.kz/ru/section/dinamika-postupleniy-nalogov-i-platezhey-v-nacionalnyy-fond),
one by-tax workbook per year, read by row label; a workbook is kept only if its tax rows add up to
«ИТОГО по налоговым поступлениям» in every month (2005 does not; there is no 2006 file). Loaded once
on 2026-09-26 by `scripts/load_nf_receipts_history.py` (the page has not been updated since May 2025);
the workbooks are archived as `data/raw/minfin/minfin_nf_receipts_history_kgd_<year>_2026-09-26.*`.
The Minfin fetcher prepends the months before 2018 to the seven `NF_*_YTD` tax series while KGD
equals Minfin in every December both cover (2018–2024: all seven taxes, to the thousand tenge).
